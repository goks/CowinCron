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
        # https_proxy = "https://103.146.176.124:80"
        # self.proxyDict = { 
        #             "https" : https_proxy, 
        #             }
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
        resp = requests.get(url + tail, headers= self.HEADERS)
        print(url+tail)
        if resp.status_code!=200:
            print('URL REQUEST FAIL.CODE: ',resp.status_code)
            return []
        self.data = resp.json()
        print("No of centres: ", len(self.data["centers"]))
        self.centres = self.data["centers"]
        return self.centres
    def process_states(self):
        url = "https://cdn-api.co-vin.in/api/v2/admin/location/states"
        resp = requests.get(url)
        if resp.status_code!=200:
            print('URL REQUEST FAIL.CODE: ',resp.status_code)
            return False
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
            if resp.status_code!=200:
                print('URL REQUEST FAIL.CODE: ',resp.status_code)
                return False
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
        FirebaseOperations().push_states(self.states_dict)
        return
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
        FirebaseOperations().push_districts(self.state_to_district_dict, self.total_district_dict)
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
        contact = self.pb.new_chat("NEW", email)
        self.pb.push_note('Registered to COWIN Cron Service', 'You will receive notifs if vaccine slots if any are found.', chat=contact)
        return contact        

class CronJob:
    def __init__(self, ):
        self.cowinParser=CowinParser()
        self.pushBullet = PushBullet()
        self.firebaseOperations = FirebaseOperations()
        return
    def execute_one_check(self):
        self.data = self.firebaseOperations.pull_data()
        for key in self.data:
            each = self.data[key]
            email = each['email']
            print("Begin searching for ",email)
            searchBy = each["searchBy"]
            if each["youngOnly"]:
                youngOnly=True
            else:
                youngOnly=False    
            if searchBy=="district":
                district = each['district']
                # state = each['state']
                district_id = each['district_code']
            elif searchBy=="pincode":
                pincode = each['pincode']
            else:
                print("Invalid searchby tag.Skipping")    
                continue
            try:
                count = each['notification_count']
            except KeyError:
                count=0    
            if(searchBy=="district"):
                # district_id = self.cowinParser.get_district_id(state,district)
                if not district_id:
                    print("Keyerror in state/district .Skipping")    
                    continue
                centres = self.cowinParser.get_centres_by_calendarBydistrict(district_id)
                no_of_centres = len(centres)
                vaccinationCentreList = VaccinationCentreList()
                vaccinationCentreList.process(centres, youngOnly)
                vaccentreList = vaccinationCentreList.getVaccinationCentreList()
                if vaccentreList == []:
                    print(" No Vaccination centres for ", email)
                    self.firebaseOperations.push_last_msg(key, email, "No Vaccination centres", '',count, no_of_centres, 0)
                    continue
                msg_body = ''
                msg_title = 'Vaccination centres found at ' + district
                for centre in vaccentreList:
                    msg_body+= centre.format_data()
                count+=1    
                self.firebaseOperations.push_last_msg(key, email, msg_title, msg_body,count,no_of_centres, len(vaccentreList))
                status = self.pushBullet.send_msg_to_contact(email, msg_title, msg_body )
                return

class FirebaseOperations:
    def __init__(self):
        credential_1 = os.environ.get('COWINCRON_CRED_1')
        credential_2 = os.environ.get('COWINCRON_CRED_2')
        credential_1 = json.loads(credential_1)
        credential_2 = json.loads(credential_2)
        credential_1.update(credential_2)
        cred = credentials.Certificate(credential_1)
        firebase_admin.initialize_app(cred, {'databaseURL': "https://cowincron-default-rtdb.asia-southeast1.firebasedatabase.app/"})  
        return
    def push_last_msg(self,key, email, title, body, count, no_of_centres, open_centres):
        ref = db.reference('usersf/')  
        # a= ref.order_by_child("email").equal_to(email).get()
        # key = int(next(iter(a)))
        dt = datetime.datetime.now(datetime.timezone.utc)
        utc_time = dt.replace(tzinfo=datetime.timezone.utc)
        utc_timestamp = utc_time.timestamp()
        ref.child(str(key)).update({"last_msg_title":title,
                            "last_msg_body":body,
                            "last_msg_time":utc_timestamp,
                            'notification_count':count,
                            'total_centres':no_of_centres,
                            'open_centres':open_centres})                                               
        return   
    def push_states(self,state_dict):
        ref = db.reference('states')
        ref.set(state_dict)
        return   
    def push_districts(self,state_to_district_dict,total_district_dict ):
        ref = db.reference('state_to_district')
        ref.set(state_to_district_dict)
        ref = db.reference('total_district')
        ref.set(total_district_dict)
        return                                                                 
    def pull_data(self):
        ref = db.reference('usersf')
        # print(ref.get())
        return(ref.get())

c = CronJob()
c.execute_one_check()

scheduler = BlockingScheduler()
scheduler.add_job(c.execute_one_check, 'interval', minutes=30)
scheduler.start()
