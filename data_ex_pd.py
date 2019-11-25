import pandas as pd
import numpy as np

patients = pd.read_csv("datasets/patients.csv",
                        usecols=['Id', 'BIRTHDATE', 'DEATHDATE'],
                        parse_dates=['BIRTHDATE', 'DEATHDATE'],
                        index_col='Id')

encounters = pd.read_csv("datasets/encounters.csv",
                        usecols=['PATIENT', 'Id', 'START', 'STOP', 'REASONCODE'],
                        parse_dates=['START', 'STOP'])

medicines = pd.read_csv("datasets/medications.csv",
                        usecols=['START', 'STOP', 'PATIENT', 'DESCRIPTION'],
                        parse_dates=['START', 'STOP'],)


encounters.rename(columns=({'PATIENT':'PATIENT_ID', 'Id':'ENCOUNTER_ID',
                             'START':'HOSPITAL_ENCOUNTER_DATE', 'STOP':'STOP',
                             'REASONCODE':'REASONCODE'}), inplace=True)


encounters.set_index('ENCOUNTER_ID', inplace=True)
# Filter non-overdose encounters and drop reasoncode column
encounters.drop(encounters[encounters.REASONCODE != 55680006].index, inplace=True)
encounters.drop('REASONCODE', axis=1, inplace=True)

# Filter encounters out of valid date range
encounters.drop(encounters[encounters.HOSPITAL_ENCOUNTER_DATE < pd.Timestamp(1999, 7, 15)].index, inplace=True)

# Filter patients with no overdoses to reduce age calc operations
patients = patients[patients.index.isin(encounters.PATIENT_ID)]

# Set ages and filter invalid encounters due to age
birthdays = patients.BIRTHDATE[encounters.PATIENT_ID]
encounters['AGE_AT_VISIT'] = (encounters['STOP'] - birthdays.values)/ np.timedelta64(1, 'Y')
encounters.drop(encounters.loc[(encounters.AGE_AT_VISIT < 18) | (encounters.AGE_AT_VISIT >= 36)].index, inplace=True)

# Finally filter medicines/patients with no valid encounters
medicines = medicines[medicines.PATIENT.isin(encounters.PATIENT_ID)]
patients = patients[patients.index.isin(encounters.PATIENT_ID)]

# Set death indicators
deathdays = (patients.loc[:, 'DEATHDATE'])[encounters.PATIENT_ID].values
death_ind_true = encounters.STOP.values >= deathdays
encounters.loc[death_ind_true, 'DEATH_AT_VISIT_IND'] = 1


# Build medicine helper dictionary
medict = medicines.groupby('PATIENT')['START', 'STOP', 'DESCRIPTION'].apply(lambda x: x.values.tolist()).to_dict()

# Build drug count and opioid indicator helper dictionaries
valid_drugs_dict, opioid_dict = {}, {}
for row in encounters.itertuples():
    if medict.get(row.PATIENT_ID) != None:
        for v in medict[row.PATIENT_ID]:
            # v = (Start, Stop, Description)
            if v[0] < row.HOSPITAL_ENCOUNTER_DATE and (pd.isnull(v[1]) or v[1] >= row.STOP):
                if valid_drugs_dict.get(row.Index) == None:
                    valid_drugs_dict[row.Index] = 1
                else:
                    valid_drugs_dict[row.Index] += 1
                if "Hydromorphone 325 MG" in v[2] or "Oxycodone-acetaminophen 100ML" in v[2] or "Fentanyl 100 MCG" in v[2]:
                    opioid_dict[row.Index] = 1

# Set drug count and opioid indicators
encounters['COUNT_CURRENT_MEDS'] = encounters.index.map(valid_drugs_dict)
encounters['CURRENT_OPIOID_IND'] = encounters.index.map(opioid_dict)

# Build readmission indicator helpers
encounters.reset_index(inplace=True)
enc_grouped = encounters.groupby('PATIENT_ID')['ENCOUNTER_ID'].apply(lambda x: x.values)
readd_dates, readd_30 = {}, {}
encounters.set_index('ENCOUNTER_ID', inplace=True)
for i in enc_grouped:
    if len(i) > 1:
        for j in range(len(i)-1):
            next_diff = encounters.HOSPITAL_ENCOUNTER_DATE[i[j+1]]-encounters.STOP[i[j]]
            if next_diff < np.timedelta64(91, 'D'):
                readd_dates[i[j]] = encounters.HOSPITAL_ENCOUNTER_DATE[i[j+1]]
                if next_diff < np.timedelta64(31, 'D'):
                    readd_30[i[j]] = 1


# Set readmission indicators
encounters['FIRST_READMISSION_DATE'] = encounters.index.map(readd_dates)
re_90 = ~pd.isnull(encounters['FIRST_READMISSION_DATE'].values)
encounters.loc[re_90, 'READMISSION_90_DAY_IND'] = 1
encounters['READMISSION_30_DAY_IND'] = encounters.index.map(readd_30)
encounters.reset_index(inplace=True)

# Drop unneeded column and prep column order for output
encounters.drop('STOP', axis=1, inplace=True)
encounters = encounters[(['PATIENT_ID', 'ENCOUNTER_ID', 'HOSPITAL_ENCOUNTER_DATE',
                          'AGE_AT_VISIT', 'DEATH_AT_VISIT_IND', 'COUNT_CURRENT_MEDS',
                          'CURRENT_OPIOID_IND', 'READMISSION_90_DAY_IND',
                          'READMISSION_30_DAY_IND', 'FIRST_READMISSION_DATE'])]

# Fill in NA values
values = ({'COUNT_CURRENT_MEDS': 0, 'CURRENT_OPIOID_IND': 0, 'DEATH_AT_VISIT_IND': 0,
           'READMISSION_90_DAY_IND': 0, 'READMISSION_30_DAY_IND': 0, 'FIRST_READMISSION_DATE': 'NA'})
encounters = encounters.fillna(value=values)

# Write dataframe to solution.csv
encounters.to_csv(r'solution.csv', index=False)
