import type {
  HousingInstallationMapPointResponse,
  HousingInstallationResponse,
} from '../api/contracts'

export type PublicAirForceInstallation = {
  id: string
  name: string
  state: string
  municipality: string
  latitude: number
  longitude: number
  sourceIdent: string
}

// Public reference layer derived from OurAirports open airport data
// (https://davidmegginson.github.io/ourairports-data/airports.csv) and limited
// to CONUS Air Force installations with distinct public coordinates.
export const PUBLIC_AIR_FORCE_INSTALLATIONS: PublicAirForceInstallation[] = [
  { id: 'altus', name: 'Altus Air Force Base', state: 'OK', municipality: 'Altus', latitude: 34.667099, longitude: -99.266701, sourceIdent: 'KLTS' },
  { id: 'andrews', name: 'Joint Base Andrews', state: 'MD', municipality: 'Camp Springs', latitude: 38.810799, longitude: -76.866997, sourceIdent: 'KADW' },
  { id: 'arnold', name: 'Arnold Air Force Base', state: 'TN', municipality: 'Manchester', latitude: 35.392601, longitude: -86.0858, sourceIdent: 'KAYX' },
  { id: 'barksdale', name: 'Barksdale Air Force Base', state: 'LA', municipality: 'Bossier City', latitude: 32.501801, longitude: -93.662697, sourceIdent: 'KBAD' },
  { id: 'beale', name: 'Beale Air Force Base', state: 'CA', municipality: 'Beale Air Force Base', latitude: 39.136101, longitude: -121.436996, sourceIdent: 'KBAB' },
  { id: 'cannon', name: 'Cannon Air Force Base', state: 'NM', municipality: 'Clovis', latitude: 34.382801, longitude: -103.321999, sourceIdent: 'KCVS' },
  { id: 'columbus', name: 'Columbus Air Force Base', state: 'MS', municipality: 'Columbus', latitude: 33.643799, longitude: -88.443802, sourceIdent: 'KCBM' },
  { id: 'creech', name: 'Creech Air Force Base', state: 'NV', municipality: 'Indian Springs', latitude: 36.5872, longitude: -115.672997, sourceIdent: 'KINS' },
  { id: 'davis-monthan', name: 'Davis-Monthan Air Force Base', state: 'AZ', municipality: 'Tucson', latitude: 32.1665, longitude: -110.883003, sourceIdent: 'KDMA' },
  { id: 'dover', name: 'Dover Air Force Base', state: 'DE', municipality: 'Dover', latitude: 39.129501, longitude: -75.466003, sourceIdent: 'KDOV' },
  { id: 'dyess', name: 'Dyess Air Force Base', state: 'TX', municipality: 'Abilene', latitude: 32.420799, longitude: -99.854599, sourceIdent: 'KDYS' },
  { id: 'edwards', name: 'Edwards Air Force Base', state: 'CA', municipality: 'Edwards', latitude: 34.910781, longitude: -117.886391, sourceIdent: 'KEDW' },
  { id: 'ellsworth', name: 'Ellsworth Air Force Base', state: 'SD', municipality: 'Rapid City', latitude: 44.145, longitude: -103.103996, sourceIdent: 'KRCA' },
  { id: 'fairchild', name: 'Fairchild Air Force Base', state: 'WA', municipality: 'Spokane', latitude: 47.615101, longitude: -117.655998, sourceIdent: 'KSKA' },
  { id: 'fe-warren', name: 'F. E. Warren Air Force Base', state: 'WY', municipality: 'Cheyenne', latitude: 41.133302, longitude: -104.866997, sourceIdent: 'FEW' },
  { id: 'grand-forks', name: 'Grand Forks Air Force Base', state: 'ND', municipality: 'Grand Forks', latitude: 47.961102, longitude: -97.401199, sourceIdent: 'KRDR' },
  { id: 'hill', name: 'Hill Air Force Base', state: 'UT', municipality: 'Ogden', latitude: 41.12403, longitude: -111.973086, sourceIdent: 'KHIF' },
  { id: 'holloman', name: 'Holloman Air Force Base', state: 'NM', municipality: 'Alamogordo', latitude: 32.852501, longitude: -106.107002, sourceIdent: 'KHMN' },
  { id: 'langley', name: 'Langley Air Force Base', state: 'VA', municipality: 'Hampton', latitude: 37.082901, longitude: -76.360497, sourceIdent: 'KLFI' },
  { id: 'laughlin', name: 'Laughlin Air Force Base', state: 'TX', municipality: 'Del Rio', latitude: 29.359501, longitude: -100.778002, sourceIdent: 'KDLF' },
  { id: 'little-rock', name: 'Little Rock Air Force Base', state: 'AR', municipality: 'Jacksonville', latitude: 34.916901, longitude: -92.149696, sourceIdent: 'KLRF' },
  { id: 'luke', name: 'Luke Air Force Base', state: 'AZ', municipality: 'Glendale', latitude: 33.535, longitude: -112.383003, sourceIdent: 'KLUF' },
  { id: 'macdill', name: 'MacDill Air Force Base', state: 'FL', municipality: 'Tampa', latitude: 27.8493, longitude: -82.521202, sourceIdent: 'KMCF' },
  { id: 'malmstrom', name: 'Malmstrom Air Force Base', state: 'MT', municipality: 'Great Falls', latitude: 47.5047, longitude: -111.186996, sourceIdent: 'KGFA' },
  { id: 'maxwell', name: 'Maxwell Air Force Base', state: 'AL', municipality: 'Montgomery', latitude: 32.3829, longitude: -86.365799, sourceIdent: 'KMXF' },
  { id: 'mcconnell', name: 'McConnell Air Force Base', state: 'KS', municipality: 'Wichita', latitude: 37.621899, longitude: -97.268204, sourceIdent: 'KIAB' },
  { id: 'minot', name: 'Minot Air Force Base', state: 'ND', municipality: 'Minot', latitude: 48.4156, longitude: -101.358002, sourceIdent: 'KMIB' },
  { id: 'moody', name: 'Moody Air Force Base', state: 'GA', municipality: 'Valdosta', latitude: 30.9678, longitude: -83.193001, sourceIdent: 'KVAD' },
  { id: 'mountain-home', name: 'Mountain Home Air Force Base', state: 'ID', municipality: 'Mountain Home', latitude: 43.043598, longitude: -115.872002, sourceIdent: 'KMUO' },
  { id: 'nellis', name: 'Nellis Air Force Base', state: 'NV', municipality: 'Las Vegas', latitude: 36.236198, longitude: -115.033997, sourceIdent: 'KLSV' },
  { id: 'offutt', name: 'Offutt Air Force Base', state: 'NE', municipality: 'Omaha', latitude: 41.119307, longitude: -95.90851, sourceIdent: 'KOFF' },
  { id: 'robins', name: 'Robins Air Force Base', state: 'GA', municipality: 'Warner Robins', latitude: 32.640099, longitude: -83.591904, sourceIdent: 'KWRB' },
  { id: 'scott', name: 'Scott Air Force Base', state: 'IL', municipality: 'Belleville', latitude: 38.5452, longitude: -89.835197, sourceIdent: 'KBLV' },
  { id: 'seymour-johnson', name: 'Seymour Johnson Air Force Base', state: 'NC', municipality: 'Goldsboro', latitude: 35.339401, longitude: -77.960602, sourceIdent: 'KGSB' },
  { id: 'shaw', name: 'Shaw Air Force Base', state: 'SC', municipality: 'Sumter', latitude: 33.972698, longitude: -80.470596, sourceIdent: 'KSSC' },
  { id: 'sheppard', name: 'Sheppard Air Force Base', state: 'TX', municipality: 'Wichita Falls', latitude: 33.9888, longitude: -98.491898, sourceIdent: 'KSPS' },
  { id: 'tinker', name: 'Tinker Air Force Base', state: 'OK', municipality: 'Oklahoma City', latitude: 35.4147, longitude: -97.386597, sourceIdent: 'KTIK' },
  { id: 'travis', name: 'Travis Air Force Base', state: 'CA', municipality: 'Fairfield', latitude: 38.262699, longitude: -121.927002, sourceIdent: 'KSUU' },
  { id: 'tyndall', name: 'Tyndall Air Force Base', state: 'FL', municipality: 'Panama City', latitude: 30.069599, longitude: -85.575401, sourceIdent: 'KPAM' },
  { id: 'vance', name: 'Vance Air Force Base', state: 'OK', municipality: 'Enid', latitude: 36.339199, longitude: -97.916496, sourceIdent: 'KEND' },
  { id: 'whiteman', name: 'Whiteman Air Force Base', state: 'MO', municipality: 'Knob Noster', latitude: 38.730301, longitude: -93.547897, sourceIdent: 'KSZL' },
  { id: 'wright-patterson', name: 'Wright-Patterson Air Force Base', state: 'OH', municipality: 'Dayton', latitude: 39.826099, longitude: -84.048302, sourceIdent: 'KFFO' },
]

export function publicReferenceInstallations(): HousingInstallationResponse[] {
  return PUBLIC_AIR_FORCE_INSTALLATIONS.map((installation) => ({
    installation_id: installation.id,
    name: installation.name,
    majcom: 'Public reference',
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
    latitude: installation.latitude,
    longitude: installation.longitude,
    status: 'unknown',
  }))
}

export function publicReferenceById() {
  return new Map(PUBLIC_AIR_FORCE_INSTALLATIONS.map((installation) => [installation.id, installation]))
}
