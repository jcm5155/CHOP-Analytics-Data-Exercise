from datetime import date
from dateutil.relativedelta import relativedelta
import pandas as pd


class Patient():
    """Represents a single patient"""
    def __init__(self, _id, birth_date, death_date):
        self.id = _id
        self.birth_date = birth_date
        self.death_date = death_date
        # All overdose start dates for this patient
        self.encs = []

    def __repr__(self):
        return f"Patient-{self.id}"


# Grab only relevant data from datasets

# From patients.csv:
#   COLUMN      | TYPE     | DESCRIPTION
#   'Id'        | string   | Unique identifier for patient
#   'BIRTHDATE' | date     | Patient's date of birth
#   'DEATHDATE' | date/NaT | Patient's date of death

patient_csv = pd.read_csv("datasets/patients.csv",
                        usecols=['Id', 'BIRTHDATE', 'DEATHDATE'],
                        parse_dates=['BIRTHDATE', 'DEATHDATE'])

# From encounters.csv:
#   COLUMN       | TYPE    | DESCRIPTION
#   'Id'         | string  | Unique identifier for encounter
#   'START'      | date    | Encounter's start date
#   'STOP'       | date    | Encounter's stop date
#   'PATIENT'    | string  | Identifier for encounter's affected patient
#   'REASONCODE' | integer | Identifier for encounter reason

encounter_csv = pd.read_csv("datasets/encounters.csv",
                        usecols=['Id', 'START', 'STOP', 'PATIENT', 'REASONCODE'],
                        parse_dates=['START', 'STOP'])
# From medications.csv:
#   COLUMN        | TYPE     | DESCRIPTION
#   'START'       | date     | Prescription's start date
#   'STOP'        | date/NaT | Prescription's stop date
#   'PATIENT'     | string   | Identifier for prescription's affected patient
#   'DESCRIPTION' | string   | Name of prescribed drug(s)

medicine_csv = pd.read_csv("datasets/medications.csv",
                        usecols=['START', 'STOP', 'PATIENT', 'DESCRIPTION'],
                        parse_dates=['START', 'STOP'])


def build_patient_dict():
    """Build dictionary of ALL patients"""
    print('building patient dict...')

#   patient_dict = {patient id : Patient()}

    patient_dict = {}
    for i in range(len(patient_csv)):
        patient_dict[patient_csv['Id'][i]] = (Patient(patient_csv['Id'][i],
                                                  patient_csv['BIRTHDATE'][i],
                                                  patient_csv['DEATHDATE'][i]))
    return patient_dict


def build_encounter_dict(patient_dict):
    """Build dictionary of all valid encounters"""
    print('building valid encounter dict...')

# Conditions: (1) Encounter must be a drug overdose
#             (2) Encounter must occur after July 15, 1999
#             (3) Patient must be age 18-35

    encounters, valid_case, invalid_case = {}, 0, 0
    valid_date_start = date(1999, 7, 15)

    for i in range(len(encounter_csv)):
        # Check conditions (1) and (2)
        if encounter_csv['REASONCODE'][i] == 55680006 and encounter_csv['START'][i] > valid_date_start:
            curr_pt = patient_dict[encounter_csv['PATIENT'][i]]
            curr_enc_stop = encounter_csv['STOP'][i]
            curr_pt_age = relativedelta(curr_enc_stop, curr_pt.birth_date).years
            # Check condition (3)
            if 18 < curr_pt_age < 36:
                curr_enc_id = encounter_csv['Id'][i]
                curr_enc_start = encounter_csv['START'][i]
                if curr_pt.death_date <= curr_enc_stop:
                    curr_pt_death_ind = 1
                else:
                    curr_pt_death_ind = 0
                # Create new encounter dict
                # Fill in default values for things we haven't checked yet
                encounters[curr_enc_id] =  {'death_ind': curr_pt_death_ind,
                                            'patient': curr_pt,
                                            'patient_age': curr_pt_age,
                                            'start': curr_enc_start,
                                            'stop': curr_enc_stop,
                                            'drug_count': 0,
                                            'opioid_ind': 0,
                                            'readd_90': 0,
                                            'readd_30': 0,
                                            'readd_date': 'NA',}
                # Append current encounter's start date to
                # current patient's self.encs
                curr_pt.encs.append(encounters[curr_enc_id]['start'])
                # Valid encounter
                valid_case += 1
            else:
                # Patient not 18-35
                invalid_case += 1
        else:
            # Encounter not an overdose or did not occur after July 15, 1999
            invalid_case += 1

    # Count for all accounted-for encounters in encounters.csv
    print(f"{invalid_case + valid_case}/{len(encounter_csv)} encounters checked!")
    return encounters


def build_medicine_dict(encounters, patient_dict):
    """Build all relevant medicine dict"""
    print("building relevant patient med dict...")

#   {patient_id : [(descr, start, stop), (descr, start, stop)...etc]}

    pt_set = set([v['patient'] for v in encounters.values()])
    medicine_dict = {}
    for i in range(len(medicine_csv)):
        curr_pt = patient_dict[medicine_csv['PATIENT'][i]]
        # Check if current medicine encounter belongs
        # to a patient with a drug overdose encounter
        if curr_pt in pt_set:
            if not medicine_dict.get(curr_pt.id):
                # Initialize medicine_dict value
                medicine_dict[curr_pt.id] = ([(medicine_csv['DESCRIPTION'][i],
                                               medicine_csv['START'][i],
                                               medicine_csv['STOP'][i])])
            else:
                # Append to medicine_dict value
                medicine_dict[curr_pt.id].append((medicine_csv['DESCRIPTION'][i],
                                                  medicine_csv['START'][i],
                                                  medicine_csv['STOP'][i]))
    return medicine_dict


def set_additional_indicators(encounters, medicine_dict):
    """Sets both readmission and drug indicators"""
    encounters = set_readmission_indicators(encounters)
    encounters = set_drug_indicators(encounters, medicine_dict)
    return encounters


def set_readmission_indicators(encounters):
    """Set readmission indicators"""
    print("setting readmission indicators...")

# INDICATOR   TYPE        DESCRIPTION
# readd_90   | 0/1      | Readmitted for drug overdose
#            |          | within 90 days of current encounter
# readd_30   | 0/1      | Readmitted for drug overdose
#            |          | within 30 days of current encounter
# readd_date | date/NaT | Date of the first readmission for
#            |          | drug overdose within 90 days

    for e in encounters.values():
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
    return encounters


def set_drug_indicators(encounters, medicine_dict):
    """Set Drug and Opioid Indicators"""
    print("setting drug and opioid indicators...")

# INDICATOR   TYPE        DESCRIPTION
# drug_count | integer | Number of active prescriptions during encounter date
# opioid_ind | 0/1     | Active opioid prescription during encounter date

    # Opioid names to check
    fent_str = "Fentanyl 100 MCG"
    hydro_str = "Hydromorphone 325 MG"
    oxy_str = "Oxycodone-acetaminophen 100ML"

    for enc_id, curr_enc in encounters.items():
        # Check if current encounter's patient
        # has any prescription history in medicine_dict
        if medicine_dict.get(curr_enc['patient'].id):
            # List of all prescriptions for current patient
            curr_pt_meds = medicine_dict[curr_enc['patient'].id]
            for curr_med in curr_pt_meds:
                active_med = False
                med_descr = curr_med[0]
                med_start = curr_med[1]
                med_stop = curr_med[2]
                if not pd.isnull(med_stop):
                    if med_start < encounters[enc_id]['start'] < med_stop:
                        active_med = True
                else:
                    # If prescription has no stop date, assume its ongoing
                    if med_start < encounters[enc_id]['start']:
                        active_med = True
                if active_med:
                    encounters[enc_id]['drug_count'] += 1
                    # Check if prescription description
                    # meets opioid_ind conditions
                    if (fent_str in med_descr
                        or hydro_str in med_descr
                        or oxy_str in med_descr):
                        # Change opioid indicator (default is 0)
                        encounters[enc_id]['opioid_ind'] = 1
    return encounters


def write_solution_to_csv(solution_data):
    """Write relevant data to file.csv"""
    with open('file.csv', 'w') as file:
        file.write("PATIENT_ID,ENCOUNTER_ID,HOSPITAL_ENCOUNTER_DATE,AGE_AT_VISIT,DEATH_AT_VISIT_IND,COUNT_CURRENT_MEDS,CURRENT_OPIOID_IND,READMISSION_90_DAY_IND,READMISSION_30_DAY_IND,FIRST_READMISSION_DATE\n")
        for _id, en in solution_data.items():
            file.write(f"{en['patient'].id},{_id},{en['start']},{en['patient_age']},{en['death_ind']},{en['drug_count']},{en['opioid_ind']},{en['readd_90']},{en['readd_30']},{en['readd_date']}\n")
    print("file.csv created")


def main():
    patients = build_patient_dict()
    encounters = build_encounter_dict(patients)
    medicines = build_medicine_dict(encounters, patients)
    solution_data = set_additional_indicators(encounters, medicines)
    write_solution_to_csv(solution_data)


if __name__ == '__main__':
    main()
