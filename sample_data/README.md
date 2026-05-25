# Sample Data

This directory holds large reference datasets used to exercise the ingestion
pipeline against realistic, real-world inputs. It is **not checked into git**
(see the `sample_data/` entry in the repo-root `.gitignore`). Drop the files
in locally and the backend ingestion fixtures / records pipelines will find
them.

## Expected files

### CMS DE-SynPUF (Medicare fraud exemplar)

The Medicare fraud domain uses CMS's publicly released synthetic Medicare
claims data (DE-SynPUF). Download from CMS and place under `sample_data/CMS/`:

- `DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv`
- `DE1_0_2009_Beneficiary_Summary_File_Sample_1.csv`
- `DE1_0_2010_Beneficiary_Summary_File_Sample_1.csv`
- `DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.csv`
- `DE1_0_2008_to_2010_Outpatient_Claims_Sample_1.csv`
- `DE1_0_2008_to_2010_Carrier_Claims_Sample_1A.csv`
- `DE1_0_2008_to_2010_Carrier_Claims_Sample_1B.csv`
- `DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_1.csv`

Source: CMS Data → Statistics, Trends, and Reports → Medicare Claims
Synthetic Public Use Files (DE-SynPUF). The files are CSV (a couple are
> 1 GB), which is why they are kept out of git.

### NPPES NPI Registry (provider reference data)

Optional provider lookup data:

- `npidata_pfile_<dates>.csv`
- `endpoint_pfile_<dates>.csv`
- `othername_pfile_<dates>.csv`
- `pl_pfile_<dates>.csv`

Source: NPPES NPI Registry monthly Data Dissemination File from CMS.

## How the code finds these files

The records ingestion test fixtures and the `medicare_fraud_cms_desynpuf.yaml`
domain config reference files under `sample_data/CMS/` by relative path. As
long as the files exist locally with the expected names, the ingestion smoke
tests (`backend/tests/records/test_cms_ingestion.py`) and the manual end-to-end
flows will pick them up.

## Why they are gitignored

The CMS DE-SynPUF carrier claims files alone are ~2.5 GB combined; the NPI
file is over 10 GB. They exceed GitHub's 100 MB single-file limit and would
balloon clone times for everyone. They are also publicly available from CMS
and updated independently of this repo, so versioning them here adds no value.

If you need a different sample set checked in for tests, place small,
purpose-built fixtures under `backend/tests/records/fixtures/` instead — those
are tracked in git.
