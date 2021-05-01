import requests
import datetime 
import pickle
import os
import json

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

from pushbullet import Pushbullet
from apscheduler.schedulers.blocking import BlockingScheduler

class CowinParser:
    def __init__(self):
        if not self.read_state_dict():
            self.process_states() 
        print("No of states: ", len(self.states_dict))
        if not self.read_district_dict():
            self.process_districts()
        print("No of districts: ", len(self.total_district_dict))
        self.HEADERS = {
            "accept": "application/json",
            "Accept-Language": "hi_IN"
        }
    def get_centres_by_calendarBydistrict(self, district_id, date=datetime.datetime.now().strftime('%d-%m-%Y')):
        url = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByDistrict?district_id="
        tail = str(district_id)+"&date="+str(date)
        resp = requests.get(url + tail, self.HEADERS)
        self.data = resp.json()
        print("No of centres: ", len(self.data["centers"]))
        self.centres = self.data["centers"]
        return self.centres
    def process_states(self):
        url = "https://cdn-api.co-vin.in/api/v2/admin/location/states"
        resp = requests.get(url)
        states = resp.json()['states']
        self.states_dict = {}
        for state in states:
            self.states_dict[state['state_name'].lower()] = state['state_id']  
        print('Obtained state list') 
        self.write_state_dict()     
        return    
    def process_districts(self):
        url = "https://cdn-api.co-vin.in/api/v2/admin/location/districts/"
        self.total_district_dict = {}
        self.state_to_district_dict = {}
        for state_name in self.states_dict:
            state_code = self.states_dict[state_name]
            resp = requests.get(url+str(state_code))
            districts = resp.json()['districts']
            self.district_dict = {}
            print("getting district list for statecode" ,state_code)
            for district in districts:
                self.district_dict[district['district_name'].lower()] = district['district_id']  
                self.total_district_dict[district['district_id']] = district['district_name'].lower() 
            self.state_to_district_dict[state_code] = self.district_dict   
        self.write_district_dict()      
        print('Obtained district list')      
        return     
    def write_state_dict(self):
        with open('./states.sv', 'wb') as handle:
            pickle.dump(self.states_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)
            print('write state_dict success')
    def read_state_dict(self):
        try:
            with open('./states.sv', 'rb') as handle:
                self.states_dict = pickle.load(handle)               
        except FileNotFoundError:
            print("No savefile for state found")
            return False
        return True          
    def write_district_dict(self):
        with open('./district_1.sv', 'wb') as handle:
            pickle.dump(self.state_to_district_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)
        with open('./district_2.sv', 'wb') as handle:
            pickle.dump(self.total_district_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)    
        print('write district_dict success')
    def read_district_dict(self):
        try:
            with open('./district_1.sv', 'rb') as handle:
                self.state_to_district_dict = pickle.load(handle) 
            with open('./district_2.sv', 'rb') as handle:    
                self.total_district_dict = pickle.load(handle) 
        except FileNotFoundError:
            print("No savefile for district found")
            return False      
        return True   
    def get_states_dict(self):
        return self.states_dict    
    def get_total_district_dict(self):
        return self.total_district_dict 
    def get_state_to_district_dict(self):
        return self.state_to_district_dict     
    def get_district_id(self, state, district):
        state = state.lower()
        district = district.lower()
        try:
            sid = self.states_dict[state]
            did = self.state_to_district_dict[sid][district]    
        except KeyError:
            return False    
        return did

class VaccinationCentre:
    def __init__(self, centre_id, name, district_name, available_capacity, min_age_limit, vaccine, date, pincode):
        self.centre_id = str(centre_id)
        self.name = str(name)
        self.district_name = str(district_name)
        self.available_capacity = str(available_capacity)
        self.min_age_limit = str(min_age_limit)
        self.vaccine = str(vaccine)
        self.date = str(date)
        self.pincode = str(pincode)
        return
    def format_data(self):
        txt = self.available_capacity + ' slots available at ' + self.name +' on '+ self.date +' at ' + self.pincode+'.\n'
        print(txt)
        return txt


class VaccinationCentreList:
    def __init__(self):
        self.VaccinationCentreList = []
    
    def process(self, centres, youngOnly):
        self.VaccinationCentreList = []
        for centre in centres:
            centre_id = centre["center_id"]
            name = centre["name"]
            district_name = centre["district_name"]
            pincode = centre['pincode']
            for session in centre["sessions"]:
                available_capacity = session["available_capacity"]
                if available_capacity<=0:
                    continue
                min_age_limit = session["min_age_limit"]
                if youngOnly and min_age_limit>=45:
                    continue
                vaccine = session["vaccine"]
                date = session['date']
                self.VaccinationCentreList.append( VaccinationCentre(centre_id, name, district_name, available_capacity, min_age_limit, vaccine, date, pincode))
                break
    def getVaccinationCentreList(self):
        return self.VaccinationCentreList

class PushBullet:
    def __init__(self):
        self.pb = Pushbullet(os.environ.get('PUSHBULLET_MEC_API'))
        self.contacts = self.pb.chats
        return
    def push(self, title, body):
        return self.pb.push_note(title, body)
    def get_contacts(self):
        a = self.contacts[0].name
        b = self.contacts[0].email
        print(a,b)
        return self.contacts
    def send_msg_to_contact(self, email, title, body):
        contact = self.get_contact(email)
        return self.pb.push_note(title, body, chat=contact)
    def get_contact(self, email):
        for contact in self.contacts:
            if contact.email==email:
                return contact
        return None        

class CronJob:
    def __init__(self, ):
        self.cowinParser=CowinParser()
        self.pushBullet = PushBullet()
        self.firebasepull = Firebasepull()
        return
    def execute_one_check(self):
        self.data = self.firebasepull.pull_data()
        for each in self.data:
            email = each['email']
            print("Begin searching for ",email)
            searchBy = each["searchBy"]
            if each["youngonly"]:
                youngOnly=True
            else:
                youngOnly=False    
            if searchBy=="district":
                district = each['district']
                state = each['state']
            elif searchBy=="pincode":
                pincode = each['pincode']
            else:
                print("Invalid searchby tag.Skipping")    
                continue
            if(searchBy=="district"):
                district_id = self.cowinParser.get_district_id(state,district)
                if not district_id:
                    print("Keyerror in state/district .Skipping")    
                    continue
                centres = self.cowinParser.get_centres_by_calendarBydistrict(district_id)
                vaccinationCentreList = VaccinationCentreList()
                vaccinationCentreList.process(centres, youngOnly)
                vaccentreList = vaccinationCentreList.getVaccinationCentreList()
                if vaccentreList == []:
                    print(" No Vaccination centres for ", email)
                    continue
                msg_body = ''
                msg_title = 'Vaccination centres found at ' + district
                for centre in vaccentreList:
                    msg_body+= centre.format_data()
                self.pushBullet.send_msg_to_contact(email, msg_title, msg_body)

class Firebasepull:
    def __init__(self):
        credential_1 = os.environ.get('COWINCRON_CRED_1')
        credential_2 = os.environ.get('COWINCRON_CRED_2')
        credential_1 = json.loads(credential_1)
        credential_2 = json.loads(credential_2)
        credential_1.update(credential_2)
        cred = credentials.Certificate(credential_1)
        firebase_admin.initialize_app(cred, {'databaseURL': "https://cowincron-default-rtdb.asia-southeast1.firebasedatabase.app/"})  
        return
    def pull_data(self):
        ref = db.reference('users')
        return(ref.get())

c = CronJob()
c.execute_one_check()

scheduler = BlockingScheduler()
scheduler.add_job(c.execute_one_check, 'interval', minutes=30)
scheduler.start()
