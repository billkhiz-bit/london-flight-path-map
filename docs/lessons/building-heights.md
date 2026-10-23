# Building heights (the EA lidar pilot)

> **BUILDING HEIGHTS ARE CONTEXT, NEVER A SCORE (Bill, 2026-10-23).** A talk audience asked "is it the land or the
> building? A flat on a high floor hears a road differently." A building's height cannot say which floor a flat
> is on; DEFRA's road-noise model already accounts for buildings (adjusting again would double count); and planes
> over a postcode are 1,000 ft and more above any roof. So a height may only be a plain fact beside a street
> ("buildings near here: mostly 1 to 2 storeys"), and `/how-it-works/` says what the figures cannot: they are for
> the postcode near ground level, not a floor (road noise and traffic pollution can differ upstairs; aircraft noise
> changes little; worded so because road noise does not simply fall with height).
>
> **THE OPEN ROUTE.** OS's own building heights cannot feed the API or reports (its licence: ROADMAP's "What not to
> build on"). The Environment Agency's survey can: its 2022 LIDAR Composite DTM (ground) and First Return DSM
> (surface), 1 m, and the National LIDAR Programme's vegetation layer, all Open Government Licence; outlines from OS
> Open Map Local, also OGL. Both are keyless. The EA tiles come from the Defra Data Services Platform's catalogue,
> found by reading its download page's own code: `POST /backend/catalog/api/tiles/collections/survey/search` with a
> WGS84 GeoJSON polygon (`Content-Type: application/geo+json`; plain JSON is a 415), then each result's `uri`
> (`/tiles/collections/survey/<product>/<year>/<res>/<tile>`). The backend download route with
> `?subscription-key='public'` refuses (400 unencoded, 403 encoded): use the `uri`. A tile is a 5 km zip (~60 MB,
> GeoTIFF + world file); the world file gives the CENTRE of the top-left pixel, half a metre in from the corner.
> Test each download's magic bytes (`PK`), as for every download.
>
> **THE METHOD, AND WHY THE MEDIAN.** A building's height is surface minus ground over the 1 m pixels inside its
> outline (centre of the outline inside the council's REAL boundary, never its bounding box), read tile by tile so
> an outline across a tile edge is measured from every tile it touches, tree pixels dropped. The first storey rule
> used the 90th percentile (the roof's top) / 3 m and read ONE STOREY HIGH against OpenStreetMap (+1.0; 47% exact):
> a pitched roof's ridge is not a floor. The MEDIAN roof / 3 m has no bias, 74% exact and 96% within one storey
> (842 OSM buildings with `building:levels`): 99% for 1-2 storeys, 93% for 3-4, 76% for 5-9; towers of 10+ read about
> 3 low on 14 buildings, NOT a podium effect (a rule taking the top where it stood well above the middle changed
> nothing); survey timing or taller storeys, unresolved. So a fact speaks in BANDS ("10 storeys or more"). OSM is
> under the ODbL: it is read as a check, counted, and never stored or published.
>
> **NEAR A POSTCODE, TWO WAYS.** A postcode is a point here (NSPL's grid reference), so the fact is about buildings
> NEAR it (50 m), not "your building", with sheds and garages out (footprint under 40 m2: 32% of the outlines are
> under 6 m tall). Counted by BUILDINGS (each once) or by FLOOR SPACE (footprint x storeys, nearer to where people
> live), they differ for 12.7% of Hounslow's postcodes, a block of flats among houses. Ties go to the lower band, so
> a street is never overstated (tested, proven red). Matching each ADDRESS to its building would need ONS's address
> file, whose postcodes ONS told a freedom-of-information request it has "no formal agreement" over: ask ONS first.
>
> **THE PILOT, 2026-10-23 (branch `lidar-building-heights-pilot`).** Hounslow: 8 tiles, 1.6 GB in gitignored
> `data/lidar/`; 26,535 of 26,687 buildings measured; 4,933 postcodes, 57 with no measured building within 50 m.
> Bill's calls outstanding: buildings or floor space, where it shows, scale up (London about 70 tiles, a day;
> Cardiff needs Natural Resources Wales' survey; New York and the Bay Area have their own open heights) or not.
> The Blender session's Hounslow flyover (`code\skyscore-blender`) uses the same EA heights.
