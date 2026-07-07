declare module 'us-atlas/states-albers-10m.json' {
  import type { GeometryCollection, Topology } from 'topojson-specification'

  interface UsAtlasStateProperties {
    name: string
  }

  const usAtlasStates: Topology<{ states: GeometryCollection<UsAtlasStateProperties> }>
  export default usAtlasStates
}
