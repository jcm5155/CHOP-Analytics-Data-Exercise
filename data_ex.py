import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import re


class Patient():
    def __init__(self, id, birth_date, death_date):
        self.id = id
        self.birth_date = birth_date
        self.death_date = death_date
        # list of all patient overdose encounters
        self.encs = []
        # list of all medicine encounters
        self.meds = []

    def __repr__(self):
        return f"Patient-{self.id}"

# regex patterns for check_opioid
hydro_pattern = re.compile(r"(Hydromorphone)")
fent_pattern = re.compile(r"(Fentanyl)")
oxy_pattern = re.compile(r"(Oxycodone-acetaminophen)")


# returns True if any of our desired opioid names are found in a medicine's description string
def check_opioid(med_str):
    is_hydro = re.findall(hydro_pattern, med_str)
    is_fent = re.findall(fent_pattern, med_str)
    is_oxy = re.findall(oxy_pattern, med_str)
    if is_oxy or is_fent or is_hydro:
        return True
    return False


dp = pd.read_csv("datasets/patients.csv",
                usecols=['Id', 'BIRTHDATE', 'DEATHDATE'],
                parse_dates=['BIRTHDATE', 'DEATHDATE'])

# build dictionary of all patients = {id: Patient()}
print('building patient list...')
patients = {}
for i in range(len(dp)):
    patients[dp['Id'][i]] = Patient(dp['Id'][i], dp['BIRTHDATE'][i], dp['DEATHDATE'][i])

de = pd.read_csv("datasets/encounters.csv",
                usecols=['Id', 'START', 'STOP', 'PATIENT', 'REASONCODE'],
                parse_dates=['START', 'STOP'])

encounters = {}
valid_case = 0
invalid_case = 0
# build dictionary of valid encounters
print('building valid encounter dict...')
for i in range(len(de)):
    if de['REASONCODE'][i] == 55680006 and de['START'][i] > datetime.date(1999, 7, 15):
            encounter_id = de['Id'][i]
            patient = patients[de['PATIENT'][i]]
            patient_age = relativedelta(de['STOP'][i], patient.birth_date).years
            if 18 < patient_age < 36:
                # valid encounter
                valid_case += 1
                # create new encounter dict, fill in default values for things we haven't checked yet
                encounters[encounter_id] = {'patient': patient, 
                                            'patient_age': patient_age,
                                            'start': de['START'][i],
                                            'stop': de['STOP'][i],
                                            'death_ind': 0,
                                            'readd_90': 0,
                                            'readd_30': 0,
                                            'readd_date': 'NA',
                                            'drug_count': 0,
                                            'opioid_ind': 0}
                patient.encs.append(encounters[encounter_id]['start'])
                if patient.death_date <= encounters[encounter_id]['stop']:
                    encounters[encounter_id]['death_ind'] = 1
            else:
                # patient not 18-35
                invalid_case += 1
    else:
        # encounter not an overdose or did not occur after July 15, 1999
        invalid_case += 1

# count for all accounted-for encounters in encounters.csv
print(f"{invalid_case + valid_case}/{len(de)} encounters checked! {valid_case} valid encounters found...")

# set readmission indicators
print("setting readmission indicators...")
for id, e in encounters.items():
    sorted_pt_encs = sorted(e['patient'].encs)
    if len(sorted_pt_encs) > 1:
        for i in range(len(sorted_pt_encs)-1):
            if sorted_pt_encs[i] == e['start']:
                readd_diff = (sorted_pt_encs[i+1] - e['stop']).days
                if readd_diff < 91:
                    e['readd_90'] = 1
                    if readd_diff < 31:
                        e['readd_30'] = 1
                    e['readd_date'] = sorted_pt_encs[i+1]


dm = pd.read_csv("datasets/medications.csv",
                usecols=['START', 'STOP', 'PATIENT', 'DESCRIPTION'],
                parse_dates=['START', 'STOP'])

pt_set = [v['patient'] for _,v in encounters.items()]

# build all relevant medicine dict = {patient_id : [(descr, start, stop), (descr, start, stop)...etc]}
meds = {}
print("building relevant patient med dict...")
for i in range(len(dm)):
    curr_pt = patients[dm['PATIENT'][i]]
    if curr_pt in pt_set:
        if not meds.get(curr_pt.id):
            meds[curr_pt.id] = ([(dm['DESCRIPTION'][i],
                                 dm['START'][i],
                                 dm['STOP'][i])])
        else:
            meds[curr_pt.id].append((dm['DESCRIPTION'][i],
                                 dm['START'][i],
                                 dm['STOP'][i]))

# set drug and opioid indicators
print("setting drug and opioid indicators...")
for k,v in encounters.items():
    if meds.get(v['patient'].id):
        curr_pt_meds = meds[v['patient'].id]
        for med in curr_pt_meds:
            descr = med[0]
            start = med[1]
            stop = med[2]
            try:
                if start < encounters[k]['start'] < stop:
                    encounters[k]['drug_count'] += 1
                    if check_opioid(descr):
                        encounters[k]['opioid_ind'] = 1
            except:
                # if there's no valid date
                if -1 < (encounters[k]['start'] - start).days < 30:
                    encounters[k]['drug_count'] += 1
                    if check_opioid(descr):
                        encounters[k]['opioid_ind'] = 1


write_count = 0 
# write our relevant data to encounters dict to file.csv
with open('file.csv', 'w') as file:
    file.write('PATIENT_ID,ENCOUNTER_ID,HOSPITAL_ENCOUNTER_DATE,AGE_AT_VISIT,DEATH_AT_VISIT_IND,COUNT_CURRENT_MEDS,CURRENT_OPIOID_IND,READMISSION_90_DAY_IND,READMISSION_30_DAY_IND,FIRST_READMISSION_DATE\n')
    for id, en in encounters.items():
        file.write(f"{en['patient'].id},{id},{en['start']},{en['patient_age']},{en['death_ind']},{en['drug_count']},{en['opioid_ind']},{en['readd_90']},{en['readd_30']},{en['readd_date']}\n")
        write_count += 1
        print(f"encounter {write_count}/{len(encounters)} written to file.csv")
    print("file.csv created")
