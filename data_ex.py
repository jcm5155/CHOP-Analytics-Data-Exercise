import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from re import compile, findall


class Patient():
    """Represents a single patient"""
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


patient_csv = pd.read_csv("datasets/patients.csv",
                        usecols=['Id', 'BIRTHDATE', 'DEATHDATE'],
                        parse_dates=['BIRTHDATE', 'DEATHDATE'])

encounter_csv = pd.read_csv("datasets/encounters.csv",
                        usecols=['Id', 'START', 'STOP', 'PATIENT', 'REASONCODE'],
                        parse_dates=['START', 'STOP'])

medicine_csv = pd.read_csv("datasets/medications.csv",
                        usecols=['START', 'STOP', 'PATIENT', 'DESCRIPTION'],
                        parse_dates=['START', 'STOP'])

# Regex patterns for check_opioid()
hydro_pattern = compile(r"(Hydromorphone)")
fent_pattern = compile(r"(Fentanyl)")
oxy_pattern = compile(r"(Oxycodone-acetaminophen)")


def check_opioid(descr):
    """
    Returns True if any relevant opioid names
    are found in medicine description
    Opioids to find: (1) Hydromorphone
                     (2) Fentanyl
                     (3) Oxycodone-acetaminophen
    """
    is_hydro = findall(hydro_pattern, descr)
    is_fent = findall(fent_pattern, descr)
    is_oxy = findall(oxy_pattern, descr)
    if is_oxy or is_fent or is_hydro:
        return True
    return False


def build_patient_dict():
    """
    Build dictionary of all patients
    {patient id : Patient()}
    """
    print('building patient list...')
    patients = {}
    for i in range(len(patient_csv)):
        patients[patient_csv['Id'][i]] = (Patient(patient_csv['Id'][i],
                                          patient_csv['BIRTHDATE'][i],
                                          patient_csv['DEATHDATE'][i]))
    return patients


def build_encounter_dict(patients):
    """
    Build dictionary of all valid encounters
    Conditions: (1) Encounter must be a drug overdose (REASONCODE = 55680006)
                (2) Encounter must occur after July 15, 1999
                (3) Patient must be age 18-35
    """
    encounters, valid_case, invalid_case = {}, 0, 0
    print('building valid encounter dict...')
    for i in range(len(encounter_csv)):
        if encounter_csv['REASONCODE'][i] == 55680006 and encounter_csv['START'][i] > datetime.date(1999, 7, 15):
            encounter_id = encounter_csv['Id'][i]
            patient = patients[encounter_csv['PATIENT'][i]]
            patient_age = relativedelta(encounter_csv['STOP'][i], patient.birth_date).years
            if 18 < patient_age < 36:
                # Valid encounter
                valid_case += 1
                # Create new encounter dict, fill in default values for things we haven't checked yet
                encounters[encounter_id] = {'patient': patient, 
                                            'patient_age': patient_age,
                                            'start': encounter_csv['START'][i],
                                            'stop': encounter_csv['STOP'][i],
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
                # Patient not 18-35
                invalid_case += 1
        else:
            # Encounter not an overdose or did not occur after July 15, 1999
            invalid_case += 1

    # Count for all accounted-for encounters in encounters.csv
    print(f"{invalid_case + valid_case}/{len(encounter_csv)} encounters checked!")
    return encounters


def set_readmission_indicators(encounters):
    """
    Set readmission indicators
    readd_90  =  0 or 1
        Readmitted for drug overdose
        within 90 days of current encounter
    readd_30  =  0 or 1
        Readmitted for drug overdose
        within 30 days of current encounter
    readd_date = N/A or Timestamp
        Date of the first readmission for
        drug overdose within 90 days
    """
    print("setting readmission indicators...")
    for _, e in encounters.items():
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


def build_medicine_dict(encounters, patients):
    """
    Build all relevant medicine dict
    {patient_id : [(descr, start, stop), (descr, start, stop)...etc]}

    """
    print("building relevant patient med dict...")
    pt_set, meds = [v['patient'] for _, v in encounters.items()], {}
    for i in range(len(medicine_csv)):
        curr_pt = patients[medicine_csv['PATIENT'][i]]
        if curr_pt in pt_set:
            if not meds.get(curr_pt.id):
                meds[curr_pt.id] = ([(medicine_csv['DESCRIPTION'][i],
                                      medicine_csv['START'][i],
                                      medicine_csv['STOP'][i])])
            else:
                meds[curr_pt.id].append((medicine_csv['DESCRIPTION'][i],
                                         medicine_csv['START'][i],
                                         medicine_csv['STOP'][i]))
    return meds


def set_drug_indicators(encounters, meds):
    """
    Set Drug and Opioid Indicators
    drug_count = int
        Number of active prescriptions
        during encounter date
    opioid_ind = 0 or 1
        Active opioid prescription
        during encounter date
    """
    print("setting drug and opioid indicators...")
    for k, v in encounters.items():
        if meds.get(v['patient'].id):
            curr_pt_meds = meds[v['patient'].id]
            for med in curr_pt_meds:
                descr, start, stop = med[0], med[1], med[2]
                if not pd.isnull(stop):
                    if start < encounters[k]['start'] < stop:
                        encounters[k]['drug_count'] += 1
                        if check_opioid(descr):
                            encounters[k]['opioid_ind'] = 1
                else:
                    # If prescription has no stop date,
                    # assume it was a 30 day supply
                    if -1 < (encounters[k]['start'] - start).days < 30:
                        encounters[k]['drug_count'] += 1
                        if check_opioid(descr):
                            encounters[k]['opioid_ind'] = 1
    return encounters


def write_solution_to_csv(encounters):
    """Write relevant data to file.csv"""
    with open('file.csv', 'w') as file:
        file.write("""PATIENT_ID,ENCOUNTER_ID,HOSPITAL_ENCOUNTER_DATE,
                      AGE_AT_VISIT,DEATH_AT_VISIT_IND,COUNT_CURRENT_MEDS,
                      CURRENT_OPIOID_IND,READMISSION_90_DAY_IND,
                      READMISSION_30_DAY_IND,FIRST_READMISSION_DATE\n""")
        for id, en in encounters.items():
            file.write((f"{en['patient'].id},{id},{en['start']},
                          {en['patient_age']},{en['death_ind']},
                          {en['drug_count']},{en['opioid_ind']},
                          {en['readd_90']},{en['readd_30']},
                          {en['readd_date']}\n"))
    print("file.csv created")


def main():
    patients = build_patient_dict()
    encounters = build_encounter_dict(patients)
    encounters = set_readmission_indicators(encounters)
    meds = build_medicine_dict(encounters, patients)
    encounters = set_drug_indicators(encounters, meds)
    write_solution_to_csv(encounters)


if __name__ == '__main__':
    main()
