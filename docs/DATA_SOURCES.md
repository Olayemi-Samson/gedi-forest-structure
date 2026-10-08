# Data sources and licences

## GEDI L2A (not redistributed)

NASA Global Ecosystem Dynamics Investigation, Level 2A *Elevation and Height
Metrics* (`GEDI02_A`), distributed by NASA's LP DAAC. Downloaded on demand with
the `earthaccess` library using your own free Earthdata login. Cite the product
version you download, as given on its LP DAAC landing page.

The reader expects, per beam group (`BEAM0000`, `BEAM0001`, `BEAM0010`,
`BEAM0011`, `BEAM0101`, `BEAM0110`, `BEAM1000`, `BEAM1011`): `shot_number`,
`delta_time`, `lat_lowestmode`, `lon_lowestmode`, `quality_flag`,
`degrade_flag`, `sensitivity`, `rh` (N x 101); optional `elev_lowestmode`.
These names match NASA's published GEDI L2A V2 Python tutorial
(nasa/GEDI-Data-Resources). If a granule lacks any required dataset the reader
stops with `SchemaError` naming what is missing.

## Administrative boundaries (bundled)

From [geoBoundaries](https://www.geoboundaries.org) (gbOpen, simplified, ADM1,
build date 12 Dec 2023). Licence is set per country; the metadata files are
bundled next to the data.

| Country | Features | Source | Licence | Bundled |
|---|---|---|---|---|
| Nigeria (NGA) | 37 (36 states + FCT) | GRID3 | CC BY 4.0 | Yes |
| Brazil (BRA) | 27 (26 states + DF) | geoBoundaries, Wikimedia Commons | CC BY 2.5 Generic | Yes |
| DR Congo (COD) | 26 | OpenStreetMap | ODbL 1.0 (share-alike) | No: `regions-fetch` |
| Indonesia (IDN) | 34 | OpenStreetMap | ODbL 1.0 (share-alike) | No: `regions-fetch` |

ODbL countries are not bundled so this MIT-licensed repository does not mix in
share-alike data. If you fetch and redistribute them, follow ODbL.

Known quirk: the Brazil file contains two misspelled state names in the source
("Rio Granda do Norte", "Rio de Jeneiro"). They are kept as published.

Citation: Runfola, D. et al. (2020). geoBoundaries: A global database of
political administrative boundaries. *PLoS ONE* 15(4): e0231866.

## Forest loss (not redistributed)

Hansen, M. C. et al. (2013). High-resolution global maps of 21st-century forest
cover change. *Science* 342(6160): 850-853. Licence: CC BY 4.0 (as stated in the
Google Earth Engine catalogue entry). Bands used: `treecover2000` (percent
canopy cover in 2000) and `lossyear` (0 = no loss; 1..N = loss in 2000 + N).
The Earth Engine catalogue lists v1.11 (2000-2023) as superseded by v1.13; use
tiles from one product version for both layers (the code errors if grids differ).
