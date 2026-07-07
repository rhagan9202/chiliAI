import type {
  HousingInstallationMapPointResponse,
  HousingInstallationResponse,
} from '../api/contracts'

export type PublicAirForceInstallation = {
  id: string
  name: string
  branch: 'USAF' | 'USSF'
  command: string
  state: string
  municipality: string
  latitude: number
  longitude: number
  hostUnit: string
  sourceIdent: string
}

// Public reference layer for CONUS Air Force and Space Force major installations.
// Compiled 2026-07-06 from official DAF/USSF sources (af.mil / spaceforce.mil base
// and MAJCOM/FLDCOM pages) with coordinates from OurAirports open airport data
// (https://davidmegginson.github.io/ourairports-data/airports.csv). The canonical
// copy of this dataset (with per-row source notes and the inclusion rule) lives at
// docs/testing/knowledge_base_fixtures/air_force_housing/installations_reference.csv
// and its colocated INSTALLATIONS.md; keep the two in sync (enforced by
// src/data/__tests__/airForceInstallations.test.ts).
export const PUBLIC_AIR_FORCE_INSTALLATIONS: PublicAirForceInstallation[] = [
  { id: 'jb_langley_eustis', name: 'Joint Base Langley-Eustis', branch: 'USAF', command: 'ACC', state: 'VA', municipality: 'Hampton', latitude: 37.082901, longitude: -76.360497, hostUnit: '633d Air Base Wing', sourceIdent: 'KLFI' },
  { id: 'seymour_johnson_afb', name: 'Seymour Johnson AFB', branch: 'USAF', command: 'ACC', state: 'NC', municipality: 'Goldsboro', latitude: 35.339401, longitude: -77.960602, hostUnit: '4th Fighter Wing', sourceIdent: 'KGSB' },
  { id: 'shaw_afb', name: 'Shaw AFB', branch: 'USAF', command: 'ACC', state: 'SC', municipality: 'Sumter', latitude: 33.972698, longitude: -80.470596, hostUnit: '20th Fighter Wing', sourceIdent: 'KSSC' },
  { id: 'moody_afb', name: 'Moody AFB', branch: 'USAF', command: 'ACC', state: 'GA', municipality: 'Valdosta', latitude: 30.967800, longitude: -83.193001, hostUnit: '23d Wing', sourceIdent: 'KVAD' },
  { id: 'mountain_home_afb', name: 'Mountain Home AFB', branch: 'USAF', command: 'ACC', state: 'ID', municipality: 'Mountain Home', latitude: 43.043598, longitude: -115.872002, hostUnit: '366th Fighter Wing', sourceIdent: 'KMUO' },
  { id: 'nellis_afb', name: 'Nellis AFB', branch: 'USAF', command: 'ACC', state: 'NV', municipality: 'Las Vegas', latitude: 36.236198, longitude: -115.033997, hostUnit: '99th Air Base Wing', sourceIdent: 'KLSV' },
  { id: 'creech_afb', name: 'Creech AFB', branch: 'USAF', command: 'ACC', state: 'NV', municipality: 'Indian Springs', latitude: 36.587200, longitude: -115.672997, hostUnit: '432d Wing', sourceIdent: 'KINS' },
  { id: 'davis_monthan_afb', name: 'Davis-Monthan AFB', branch: 'USAF', command: 'ACC', state: 'AZ', municipality: 'Tucson', latitude: 32.166500, longitude: -110.883003, hostUnit: '355th Wing', sourceIdent: 'KDMA' },
  { id: 'tyndall_afb', name: 'Tyndall AFB', branch: 'USAF', command: 'ACC', state: 'FL', municipality: 'Panama City', latitude: 30.069599, longitude: -85.575401, hostUnit: '325th Fighter Wing', sourceIdent: 'KPAM' },
  { id: 'beale_afb', name: 'Beale AFB', branch: 'USAF', command: 'ACC', state: 'CA', municipality: 'Marysville', latitude: 39.136101, longitude: -121.436996, hostUnit: '9th Reconnaissance Wing', sourceIdent: 'KBAB' },
  { id: 'offutt_afb', name: 'Offutt AFB', branch: 'USAF', command: 'ACC', state: 'NE', municipality: 'Bellevue', latitude: 41.119307, longitude: -95.908510, hostUnit: '55th Wing', sourceIdent: 'KOFF' },
  { id: 'grand_forks_afb', name: 'Grand Forks AFB', branch: 'USAF', command: 'ACC', state: 'ND', municipality: 'Grand Forks', latitude: 47.961102, longitude: -97.401199, hostUnit: '319th Reconnaissance Wing', sourceIdent: 'KRDR' },
  { id: 'holloman_afb', name: 'Holloman AFB', branch: 'USAF', command: 'ACC', state: 'NM', municipality: 'Alamogordo', latitude: 32.852501, longitude: -106.107002, hostUnit: '49th Wing', sourceIdent: 'KHMN' },
  { id: 'altus_afb', name: 'Altus AFB', branch: 'USAF', command: 'AETC', state: 'OK', municipality: 'Altus', latitude: 34.667099, longitude: -99.266701, hostUnit: '97th Air Mobility Wing', sourceIdent: 'KLTS' },
  { id: 'columbus_afb', name: 'Columbus AFB', branch: 'USAF', command: 'AETC', state: 'MS', municipality: 'Columbus', latitude: 33.643799, longitude: -88.443802, hostUnit: '14th Flying Training Wing', sourceIdent: 'KCBM' },
  { id: 'goodfellow_afb', name: 'Goodfellow AFB', branch: 'USAF', command: 'AETC', state: 'TX', municipality: 'San Angelo', latitude: 31.431630, longitude: -100.399216, hostUnit: '17th Training Wing', sourceIdent: 'US-8159' },
  { id: 'keesler_afb', name: 'Keesler AFB', branch: 'USAF', command: 'AETC', state: 'MS', municipality: 'Biloxi', latitude: 30.410400, longitude: -88.924400, hostUnit: '81st Training Wing', sourceIdent: 'KBIX' },
  { id: 'laughlin_afb', name: 'Laughlin AFB', branch: 'USAF', command: 'AETC', state: 'TX', municipality: 'Del Rio', latitude: 29.359501, longitude: -100.778002, hostUnit: '47th Flying Training Wing', sourceIdent: 'KDLF' },
  { id: 'luke_afb', name: 'Luke AFB', branch: 'USAF', command: 'AETC', state: 'AZ', municipality: 'Glendale', latitude: 33.535000, longitude: -112.383003, hostUnit: '56th Fighter Wing', sourceIdent: 'KLUF' },
  { id: 'maxwell_afb', name: 'Maxwell AFB', branch: 'USAF', command: 'AETC', state: 'AL', municipality: 'Montgomery', latitude: 32.382900, longitude: -86.365799, hostUnit: '42d Air Base Wing', sourceIdent: 'KMXF' },
  { id: 'jb_san_antonio', name: 'Joint Base San Antonio', branch: 'USAF', command: 'AETC', state: 'TX', municipality: 'San Antonio', latitude: 29.384199, longitude: -98.581100, hostUnit: '502d Air Base Wing', sourceIdent: 'KSKF' },
  { id: 'sheppard_afb', name: 'Sheppard AFB', branch: 'USAF', command: 'AETC', state: 'TX', municipality: 'Wichita Falls', latitude: 33.988800, longitude: -98.491898, hostUnit: '82d Training Wing', sourceIdent: 'KSPS' },
  { id: 'vance_afb', name: 'Vance AFB', branch: 'USAF', command: 'AETC', state: 'OK', municipality: 'Enid', latitude: 36.339199, longitude: -97.916496, hostUnit: '71st Flying Training Wing', sourceIdent: 'KEND' },
  { id: 'dover_afb', name: 'Dover AFB', branch: 'USAF', command: 'AMC', state: 'DE', municipality: 'Dover', latitude: 39.129501, longitude: -75.466003, hostUnit: '436th Airlift Wing', sourceIdent: 'KDOV' },
  { id: 'fairchild_afb', name: 'Fairchild AFB', branch: 'USAF', command: 'AMC', state: 'WA', municipality: 'Spokane', latitude: 47.615101, longitude: -117.655998, hostUnit: '92d Air Refueling Wing', sourceIdent: 'KSKA' },
  { id: 'little_rock_afb', name: 'Little Rock AFB', branch: 'USAF', command: 'AMC', state: 'AR', municipality: 'Jacksonville', latitude: 34.916901, longitude: -92.149696, hostUnit: '19th Airlift Wing', sourceIdent: 'KLRF' },
  { id: 'macdill_afb', name: 'MacDill AFB', branch: 'USAF', command: 'AMC', state: 'FL', municipality: 'Tampa', latitude: 27.849300, longitude: -82.521202, hostUnit: '6th Air Refueling Wing', sourceIdent: 'KMCF' },
  { id: 'mcconnell_afb', name: 'McConnell AFB', branch: 'USAF', command: 'AMC', state: 'KS', municipality: 'Wichita', latitude: 37.621899, longitude: -97.268204, hostUnit: '22d Air Refueling Wing', sourceIdent: 'KIAB' },
  { id: 'scott_afb', name: 'Scott AFB', branch: 'USAF', command: 'AMC', state: 'IL', municipality: 'Belleville', latitude: 38.545200, longitude: -89.835197, hostUnit: '375th Air Mobility Wing', sourceIdent: 'KBLV' },
  { id: 'travis_afb', name: 'Travis AFB', branch: 'USAF', command: 'AMC', state: 'CA', municipality: 'Fairfield', latitude: 38.262699, longitude: -121.927002, hostUnit: '60th Air Mobility Wing', sourceIdent: 'KSUU' },
  { id: 'jb_charleston', name: 'Joint Base Charleston', branch: 'USAF', command: 'AMC', state: 'SC', municipality: 'Charleston', latitude: 32.896159, longitude: -80.038151, hostUnit: '628th Air Base Wing', sourceIdent: 'KCHS' },
  { id: 'jb_mcguire_dix_lakehurst', name: 'Joint Base McGuire-Dix-Lakehurst', branch: 'USAF', command: 'AMC', state: 'NJ', municipality: 'Wrightstown', latitude: 40.015598, longitude: -74.591698, hostUnit: '87th Air Base Wing', sourceIdent: 'KWRI' },
  { id: 'barksdale_afb', name: 'Barksdale AFB', branch: 'USAF', command: 'AFGSC', state: 'LA', municipality: 'Bossier City', latitude: 32.501801, longitude: -93.662697, hostUnit: '2d Bomb Wing', sourceIdent: 'KBAD' },
  { id: 'dyess_afb', name: 'Dyess AFB', branch: 'USAF', command: 'AFGSC', state: 'TX', municipality: 'Abilene', latitude: 32.420799, longitude: -99.854599, hostUnit: '7th Bomb Wing', sourceIdent: 'KDYS' },
  { id: 'ellsworth_afb', name: 'Ellsworth AFB', branch: 'USAF', command: 'AFGSC', state: 'SD', municipality: 'Box Elder', latitude: 44.145000, longitude: -103.103996, hostUnit: '28th Bomb Wing', sourceIdent: 'KRCA' },
  { id: 'fe_warren_afb', name: 'Francis E. Warren AFB', branch: 'USAF', command: 'AFGSC', state: 'WY', municipality: 'Cheyenne', latitude: 41.133302, longitude: -104.866997, hostUnit: '90th Missile Wing', sourceIdent: 'FEW' },
  { id: 'malmstrom_afb', name: 'Malmstrom AFB', branch: 'USAF', command: 'AFGSC', state: 'MT', municipality: 'Great Falls', latitude: 47.504700, longitude: -111.186996, hostUnit: '341st Missile Wing', sourceIdent: 'KGFA' },
  { id: 'minot_afb', name: 'Minot AFB', branch: 'USAF', command: 'AFGSC', state: 'ND', municipality: 'Minot', latitude: 48.415600, longitude: -101.358002, hostUnit: '5th Bomb Wing', sourceIdent: 'KMIB' },
  { id: 'whiteman_afb', name: 'Whiteman AFB', branch: 'USAF', command: 'AFGSC', state: 'MO', municipality: 'Knob Noster', latitude: 38.730301, longitude: -93.547897, hostUnit: '509th Bomb Wing', sourceIdent: 'KSZL' },
  { id: 'kirtland_afb', name: 'Kirtland AFB', branch: 'USAF', command: 'AFGSC', state: 'NM', municipality: 'Albuquerque', latitude: 35.039976, longitude: -106.608925, hostUnit: '377th Air Base Wing', sourceIdent: 'KABQ' },
  { id: 'edwards_afb', name: 'Edwards AFB', branch: 'USAF', command: 'AFMC', state: 'CA', municipality: 'Edwards', latitude: 34.910781, longitude: -117.886391, hostUnit: '412th Test Wing', sourceIdent: 'KEDW' },
  { id: 'eglin_afb', name: 'Eglin AFB', branch: 'USAF', command: 'AFMC', state: 'FL', municipality: 'Valparaiso', latitude: 30.481315, longitude: -86.515839, hostUnit: '96th Test Wing', sourceIdent: 'KVPS' },
  { id: 'hanscom_afb', name: 'Hanscom AFB', branch: 'USAF', command: 'AFMC', state: 'MA', municipality: 'Bedford', latitude: 42.470001, longitude: -71.289001, hostUnit: '66th Air Base Group', sourceIdent: 'KBED' },
  { id: 'hill_afb', name: 'Hill AFB', branch: 'USAF', command: 'AFMC', state: 'UT', municipality: 'Ogden', latitude: 41.124030, longitude: -111.973086, hostUnit: '75th Air Base Wing', sourceIdent: 'KHIF' },
  { id: 'robins_afb', name: 'Robins AFB', branch: 'USAF', command: 'AFMC', state: 'GA', municipality: 'Warner Robins', latitude: 32.640099, longitude: -83.591904, hostUnit: '78th Air Base Wing', sourceIdent: 'KWRB' },
  { id: 'tinker_afb', name: 'Tinker AFB', branch: 'USAF', command: 'AFMC', state: 'OK', municipality: 'Oklahoma City', latitude: 35.414700, longitude: -97.386597, hostUnit: '72d Air Base Wing', sourceIdent: 'KTIK' },
  { id: 'wright_patterson_afb', name: 'Wright-Patterson AFB', branch: 'USAF', command: 'AFMC', state: 'OH', municipality: 'Dayton', latitude: 39.826099, longitude: -84.048302, hostUnit: '88th Air Base Wing', sourceIdent: 'KFFO' },
  { id: 'arnold_afb', name: 'Arnold AFB', branch: 'USAF', command: 'AFMC', state: 'TN', municipality: 'Tullahoma', latitude: 35.392601, longitude: -86.085800, hostUnit: 'Arnold Engineering Development Complex', sourceIdent: 'KAYX' },
  { id: 'hurlburt_field', name: 'Hurlburt Field', branch: 'USAF', command: 'AFSOC', state: 'FL', municipality: 'Mary Esther', latitude: 30.427799, longitude: -86.689301, hostUnit: '1st Special Operations Wing', sourceIdent: 'KHRT' },
  { id: 'cannon_afb', name: 'Cannon AFB', branch: 'USAF', command: 'AFSOC', state: 'NM', municipality: 'Clovis', latitude: 34.382801, longitude: -103.321999, hostUnit: '27th Special Operations Wing', sourceIdent: 'KCVS' },
  { id: 'jb_andrews', name: 'Joint Base Andrews', branch: 'USAF', command: 'AFDW', state: 'MD', municipality: 'Camp Springs', latitude: 38.810799, longitude: -76.866997, hostUnit: '316th Wing', sourceIdent: 'KADW' },
  { id: 'jb_anacostia_bolling', name: 'Joint Base Anacostia-Bolling', branch: 'USAF', command: 'AFDW', state: 'DC', municipality: 'Washington', latitude: 38.842800, longitude: -77.016100, hostUnit: '11th Wing', sourceIdent: '' },
  { id: 'usafa', name: 'US Air Force Academy', branch: 'USAF', command: 'USAFA', state: 'CO', municipality: 'Colorado Springs', latitude: 38.972497, longitude: -104.821125, hostUnit: '10th Air Base Wing', sourceIdent: 'KAFF' },
  { id: 'dobbins_arb', name: 'Dobbins ARB', branch: 'USAF', command: 'AFRC', state: 'GA', municipality: 'Marietta', latitude: 33.915401, longitude: -84.516296, hostUnit: '94th Airlift Wing', sourceIdent: 'KMGE' },
  { id: 'grissom_arb', name: 'Grissom ARB', branch: 'USAF', command: 'AFRC', state: 'IN', municipality: 'Peru', latitude: 40.648102, longitude: -86.152100, hostUnit: '434th Air Refueling Wing', sourceIdent: 'KGUS' },
  { id: 'homestead_arb', name: 'Homestead ARB', branch: 'USAF', command: 'AFRC', state: 'FL', municipality: 'Homestead', latitude: 25.488600, longitude: -80.383598, hostUnit: '482d Fighter Wing', sourceIdent: 'KHST' },
  { id: 'march_arb', name: 'March ARB', branch: 'USAF', command: 'AFRC', state: 'CA', municipality: 'Riverside', latitude: 33.880699, longitude: -117.259003, hostUnit: '452d Air Mobility Wing', sourceIdent: 'KRIV' },
  { id: 'westover_arb', name: 'Westover ARB', branch: 'USAF', command: 'AFRC', state: 'MA', municipality: 'Chicopee', latitude: 42.194000, longitude: -72.534798, hostUnit: '439th Airlift Wing', sourceIdent: 'KCEF' },
  { id: 'peterson_sfb', name: 'Peterson SFB', branch: 'USSF', command: 'SpOC', state: 'CO', municipality: 'Colorado Springs', latitude: 38.815800, longitude: -104.700800, hostUnit: 'Space Base Delta 1', sourceIdent: 'KCOS' },
  { id: 'schriever_sfb', name: 'Schriever SFB', branch: 'USSF', command: 'SpOC', state: 'CO', municipality: 'Colorado Springs', latitude: 38.803100, longitude: -104.528900, hostUnit: 'Space Base Delta 41', sourceIdent: '' },
  { id: 'buckley_sfb', name: 'Buckley SFB', branch: 'USSF', command: 'SpOC', state: 'CO', municipality: 'Aurora', latitude: 39.701698, longitude: -104.751999, hostUnit: 'Space Base Delta 2', sourceIdent: 'KBKF' },
  { id: 'vandenberg_sfb', name: 'Vandenberg SFB', branch: 'USSF', command: 'SSC', state: 'CA', municipality: 'Lompoc', latitude: 34.737301, longitude: -120.584000, hostUnit: 'Space Launch Delta 30', sourceIdent: 'KVBG' },
  { id: 'patrick_sfb', name: 'Patrick SFB', branch: 'USSF', command: 'SSC', state: 'FL', municipality: 'Satellite Beach', latitude: 28.234900, longitude: -80.610100, hostUnit: 'Space Launch Delta 45', sourceIdent: 'KCOF' },
  { id: 'cape_canaveral_sfs', name: 'Cape Canaveral SFS', branch: 'USSF', command: 'SSC', state: 'FL', municipality: 'Cocoa Beach', latitude: 28.488900, longitude: -80.577800, hostUnit: 'Space Launch Delta 45', sourceIdent: 'KXMR' },
  { id: 'los_angeles_afb', name: 'Los Angeles AFB', branch: 'USSF', command: 'SSC', state: 'CA', municipality: 'El Segundo', latitude: 33.915500, longitude: -118.382500, hostUnit: 'Space Base Delta 3', sourceIdent: '' },
]

export function publicReferenceInstallations(): HousingInstallationResponse[] {
  return PUBLIC_AIR_FORCE_INSTALLATIONS.map((installation) => ({
    installation_id: installation.id,
    name: installation.name,
    branch: installation.branch,
    majcom: installation.command,
    state: installation.state,
    status: 'unknown',
    open_work_orders: 0,
    occupancy_rate: null,
  }))
}

export function publicReferenceMapPoints(): HousingInstallationMapPointResponse[] {
  return PUBLIC_AIR_FORCE_INSTALLATIONS.map((installation) => ({
    installation_id: installation.id,
    name: installation.name,
    branch: installation.branch,
    latitude: installation.latitude,
    longitude: installation.longitude,
    status: 'unknown',
  }))
}

export function publicReferenceById() {
  return new Map(PUBLIC_AIR_FORCE_INSTALLATIONS.map((installation) => [installation.id, installation]))
}
