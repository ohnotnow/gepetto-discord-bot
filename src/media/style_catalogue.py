"""
Curated style catalogue for the corpse pipeline's style slot.

History: the style slice used to be an LLM pick with an anti-list
(EVERGREEN_STYLE_BANS + the last 20 per-server picks). Production data
(2026-07-19) showed the LLM's effective repertoire was only ~50 favourites:
the same artists recurred on every server, and each favourite returned
within a run or two of falling off the 20-item exclusion window (Mary Blair
on three servers inside a week). The catalogue replaces the LLM prior as the
randomness source; the LLM still does all the creative assembly downstream.
The catalogue is never sent to a model, so its size costs nothing.

Entries are (key, description):

- key: a distinctive substring used for exclusion matching against recent
  style history (case-insensitive). Keys also match the free-text values the
  old LLM picker stored ("Mary Blair" matches "Mary Blair’s Disney concept
  art, bold gouache shapes…"), so pre-catalogue history still counts.
  Every key MUST appear in its own description, or a pick would never
  self-exclude — there's a test for that.
- description: the style text handed to the assembler; same shape the LLM
  picker used to produce (5-20 words, committed and specific).

Deliberately NOT included — the old evergreen bans, i.e. LLM/image-model
clichés: Dutch Golden Age, Vermeer, Hieronymus Bosch, De Chirico, Salvador
Dalí, generic surrealism, Studio Ghibli, Wes Anderson symmetry. There's a
test for those too.
"""

STYLE_CATALOGUE: list[tuple[str, str]] = [
    # ------------------------------------------------------------------
    # Painting and drawing — pre-1900
    # ------------------------------------------------------------------
    ("Giotto", "Giotto's trecento frescoes, solemn haloed figures in shallow theatrical space"),
    ("Bruegel", "Pieter Bruegel's teeming peasant panoramas, bird's-eye villages and busy seasonal labour"),
    ("Caravaggio", "Caravaggio's tenebrist Baroque drama, brutal chiaroscuro and candlelit flesh tones"),
    ("Artemisia Gentileschi", "Artemisia Gentileschi's Baroque canvases, muscular candlelit drama and defiant gazes"),
    ("Canaletto", "Canaletto's Venetian vedute, glassy canals and precise sunlit architecture"),
    ("Hogarth", "Hogarth's satirical engravings, crowded moral chaos in Georgian London"),
    ("Turner", "J.M.W. Turner's late storm seascapes, dissolving light and furious atmospheric colour"),
    ("Constable", "Constable's English landscapes, scudding clouds, cart tracks and green river light"),
    ("Caspar David Friedrich", "Caspar David Friedrich's Romantic vistas, lone figures before vast misty sublimity"),
    ("Whistler", "Whistler's nocturnes, dissolving bridges in blue-grey tonal mist"),
    ("Sargent", "Sargent's bravura society portraits, liquid brushwork and rustling satin"),
    ("Winslow Homer", "Winslow Homer's watercolours, heaving seas, spray and stoic small boats"),
    ("Caillebotte", "Gustave Caillebotte's rainy Paris streets, wet cobbles, umbrellas and plunging perspective"),
    ("Seurat", "Seurat's pointillist riverbanks, dotted light and Sunday stillness"),
    ("Degas", "Degas's backstage pastels, tired dancers, raking light and cropped candid angles"),
    ("Toulouse-Lautrec", "Toulouse-Lautrec's cabaret posters, gaslit dancers, flat colour and brisk contour"),
    ("Munch", "Edvard Munch's anxious Symbolist paintings, swirling skies and hollow-eyed figures"),
    ("Odilon Redon", "Odilon Redon's Symbolist pastels, velvety charcoal shadows, floating florals and dreamlike jewel tones"),
    ("Gustave Doré", "Gustave Doré's engraved epics, thunderous skies and tiny figures in vast gloom"),
    ("Dürer", "Albrecht Dürer's engravings, dense crosshatching and meticulous northern detail"),

    # ------------------------------------------------------------------
    # Painting — modern movements
    # ------------------------------------------------------------------
    ("Klimt", "Gustav Klimt's Byzantine gold-leaf portraits, mosaic ornament and languid Viennese Secession elegance"),
    ("Schiele", "Egon Schiele's jagged Expressionist watercolour portraits, raw contour lines and bruised flesh tones"),
    ("Mucha", "Alphonse Mucha's Art Nouveau lithographs, flowing hair, floral halos and ornate borders"),
    ("Kirchner", "Ernst Ludwig Kirchner's Die Brücke street scenes, acid colours and jagged nervous figures"),
    ("Franz Marc", "Franz Marc's Blue Rider animals, prismatic horses in fractured chromatic landscapes"),
    ("Paul Klee", "Paul Klee's wry pictographic paintings, stitched grids, arrows and moonlit geometry"),
    ("Kandinsky", "Kandinsky's musical abstraction, colliding arcs, points and orchestral colour"),
    ("Mondrian", "Mondrian's neoplastic grids, primary blocks and severe white balance"),
    ("Malevich", "Malevich's Suprematist compositions, floating black and red geometry on white void"),
    ("El Lissitzky", "El Lissitzky's Constructivist prouns, tilted axonometric geometry and red-black dynamism"),
    ("Popova", "Lyubov Popova's Constructivist stage designs, angular planes, industrial reds and kinetic theatrical geometry"),
    ("Kupka", "František Kupka's Orphist abstraction, luminous planes, cosmic spirals and rhythmic colour geometry"),
    ("Sonia Delaunay", "Sonia Delaunay's Simultanist textiles, radiant concentric geometry and rhythmic modernist colour blocks"),
    ("Hilma af Klint", "Hilma af Klint's occult diagrams, pastel spirals, swans and cosmic botany"),
    ("Kollwitz", "Käthe Kollwitz's expressionist lithographs, raw charcoal blacks and monumental working-class tenderness"),
    ("Hannah Höch", "Hannah Höch's Dada photomontage, jagged cutouts, satirical collage and Weimar newspaper textures"),
    ("Kurt Schwitters", "Kurt Schwitters's Merz collage, tram tickets, torn wrappers and quiet composition"),
    ("Chagall", "Chagall's floating village dreamscapes, fiddlers, goats and upside-down lovers"),
    ("Modigliani", "Modigliani's almond-eyed portraits, elongated necks and warm muted planes"),
    ("Matisse", "Matisse's paper cut-outs, dancing cobalt and coral silhouettes"),
    ("Henri Rousseau", "Henri Rousseau's naïve jungles, moonlit tigers and impossible layered foliage"),
    ("Tamara de Lempicka", "Tamara de Lempicka's Art Deco portraits, polished chrome planes and icy theatrical glamour"),
    ("Remedios Varo", "Remedios Varo's alchemical dreamscapes, spindly hooded figures and clockwork contraptions"),
    ("Leonora Carrington", "Leonora Carrington's mythic tempera, pale beasts and hooded celebrants"),
    ("Frida Kahlo", "Frida Kahlo's votive portrait style, unflinching gazes amid symbolic flora and fauna"),
    ("Diego Rivera", "Diego Rivera's industrial murals, monumental workers and interlocking machinery"),
    ("Posada", "José Guadalupe Posada's calavera broadsheets, dapper skeletons in lively engraved crowds"),
    ("Tarsila do Amaral", "Tarsila do Amaral's Brazilian modernism, tropical colour, simplified forms and dreamlike monumentality"),

    # ------------------------------------------------------------------
    # Painting — American and British 20th century
    # ------------------------------------------------------------------
    ("Edward Hopper", "Edward Hopper's diner-light oil painting, lonely interiors, hard shadows and cinematic stillness"),
    ("Grant Wood", "Grant Wood's American Regionalist painting, crisp rural geometry and uncanny stillness"),
    ("Charles Sheeler", "Charles Sheeler's Precisionist industrial paintings, hard-edged factories and crystalline machine-age geometry"),
    ("Charles Burchfield", "Charles Burchfield's visionary watercolour landscapes, vibrating outlines and ecstatic weather patterns"),
    ("Andrew Wyeth", "Andrew Wyeth's dry-brush tempera, weathered farmhouses and austere windswept fields"),
    ("Georgia O'Keeffe", "Georgia O'Keeffe's desert modernism, monumental blooms, bleached bone and mesa light"),
    ("Agnes Pelton", "Agnes Pelton's desert Transcendentalist paintings, glowing orbs, soft gradients and mystical pastel radiance"),
    ("Agnes Martin", "Agnes Martin's minimalist graphite grids, pale washes and meditative hand-drawn precision"),
    ("Thiebaud", "Wayne Thiebaud's pastel impasto bakery paintings, thick shadows and playful confectionery geometry"),
    ("Alma Thomas", "Alma Thomas's mosaic abstraction, concentric daubs of jubilant colour"),
    ("Jacob Lawrence", "Jacob Lawrence's Migration Series tempera, angular figures and flat urgent colour"),
    ("Aaron Douglas", "Aaron Douglas's Harlem Renaissance murals, silhouetted figures, radiating bands and smoky ochre geometry"),
    ("Romare Bearden", "Romare Bearden's layered collage, jazz interiors cut from magazines and memory"),
    ("Ben Shahn", "Ben Shahn's social realist tempera posters, wiry ink contours and muted Depression-era palette"),
    ("Norman Rockwell", "Norman Rockwell's mischievous magazine covers, warm anecdotal detail and knowing glances"),
    ("N.C. Wyeth", "N.C. Wyeth's swashbuckling adventure oils, dramatic firelight and broad heroic brushwork"),
    ("Maxfield Parrish", "Maxfield Parrish's luminous golden-hour idylls, cobalt skies and classical daydream light"),
    ("Eric Ravilious", "Eric Ravilious's chalky watercolours, South Downs curves, rolling stock and empty rooms"),
    ("Edward Bawden", "Edward Bawden's linocuts and lithographs, dry English wit and patterned architecture"),
    ("Paul Nash", "Paul Nash's mystic English landscapes, standing stones and dream-tilted fields"),
    ("Stanley Spencer", "Stanley Spencer's Cookham scenes, tumbling villagers rendered with earthy tenderness"),
    ("Lowry", "L.S. Lowry's industrial townscapes, matchstick crowds under milky skies"),
    ("John Piper", "John Piper's romantic ruins, inky churches against streaked storm colour"),

    # ------------------------------------------------------------------
    # Painting and printmaking — contemporary
    # ------------------------------------------------------------------
    ("Faith Ringgold", "Faith Ringgold's story quilts, bold acrylic figures, patterned borders and narrative textile panels"),
    ("Kerry James Marshall", "Kerry James Marshall's monumental scenes of Black everyday life, saturated flat colour"),
    ("Kehinde Wiley", "Kehinde Wiley's ornate heroic portraiture, floral wallpaper grounds and old-master poses"),
    ("Basquiat", "Basquiat's raw crowned figures, scrawled anatomy and urgent oil-stick text"),
    ("Keith Haring", "Keith Haring's radiant line figures, thick pop outlines and dancing pictograms"),
    ("Hockney", "David Hockney's Californian pools, flat sunlit planes and a lone splash"),
    ("Peter Doig", "Peter Doig's hazy magic-realist canoes and cabins, dissolving painted reflections"),
    ("Bridget Riley", "Bridget Riley's op-art waves, vibrating monochrome stripes"),
    ("Vasarely", "Victor Vasarely's op-art grids, bulging chequerboards and chromatic illusions"),
    ("Julie Mehretu", "Julie Mehretu's layered cartographic abstraction, frenetic ink vectors and translucent architectural strata"),
    ("Kentridge", "William Kentridge's charcoal palimpsest animation, erased ghosts and smudged industrial melancholy"),
    ("Emory Douglas", "Emory Douglas's Black Panther poster graphics, bold linocut-like figures and revolutionary newsprint urgency"),
    ("Maria Prymachenko", "Maria Prymachenko's Ukrainian folk gouache, fantastical beasts in bold floral colour"),
    ("Emily Kame Kngwarreye", "Emily Kame Kngwarreye's sweeping dot-field paintings, layered desert colour"),

    # ------------------------------------------------------------------
    # East and South Asian traditions
    # ------------------------------------------------------------------
    ("Hokusai", "Hokusai's Edo-period ukiyo-e woodblocks, curling waves, crisp outlines and indigo gradients"),
    ("Hiroshige", "Hiroshige's rain-slashed woodblock landscapes, travellers on wet roads under indigo skies"),
    ("Sharaku", "Sharaku's kabuki actor prints, tense exaggerated expressions and flattened dramatic colour blocks"),
    ("Kuniyoshi", "Utagawa Kuniyoshi's warrior ukiyo-e, dynamic diagonals, bold outlines and theatrical colour"),
    ("Utamaro", "Utamaro's bijin-ga woodblock portraits, elegant elongated figures and delicate linework"),
    ("Kawase Hasui", "Kawase Hasui's shin-hanga woodblock prints, rain-slick streets, soft lantern glow and delicate gradients"),
    ("Hiroshi Yoshida", "Hiroshi Yoshida's shin-hanga mountain prints, luminous alpine light and patient gradients"),
    ("Qi Baishi", "Qi Baishi's playful ink-wash shrimp and gourds, wet blots and confident sparse strokes"),
    ("Song-dynasty", "Song-dynasty landscape scrolls, mist-wrapped mountains, tiny travellers and vast negative space"),
    ("Foujita", "Tsuguharu Foujita's milky-white ink portraiture, delicate catlike lines and pearlescent Parisian restraint"),
    ("Persian miniature", "Persian miniature painting, jewel-bright courts, patterned carpets and flattened perspective"),
    ("Mughal miniature", "Mughal miniature painting, ornate borders, processions and meticulous natural detail"),
    ("Madhubani", "Madhubani painting, double-outlined figures, fish and peacocks filling every margin"),
    ("Kalighat", "Kalighat painting, sweeping brush figures with bold outlines and satirical grace"),
    ("minhwa", "Korean minhwa folk painting, grinning tigers, magpies and flattened auspicious objects"),

    # ------------------------------------------------------------------
    # Ancient and medieval
    # ------------------------------------------------------------------
    ("illuminated manuscript", "illuminated manuscript marginalia, gilded initials, knotwork borders and mischievous beasts"),
    ("Byzantine icon", "Byzantine icon painting, gold-leaf grounds, solemn frontal saints and stylised drapery"),
    ("Pompeiian fresco", "Pompeiian fresco painting, earthy reds, faded plaster and casual domestic scenes"),
    ("red-figure pottery", "Attic red-figure pottery, terracotta and black silhouettes in athletic profile"),
    ("Egyptian tomb painting", "Egyptian tomb painting, striding profile figures, flat registers and an ochre-and-lapis palette"),
    ("Bayeux", "Bayeux Tapestry embroidery, stitched processions with captioned borders"),

    # ------------------------------------------------------------------
    # Illustration and book arts
    # ------------------------------------------------------------------
    ("Beardsley", "Aubrey Beardsley's ink decadence, sinuous black masses and elegant grotesques"),
    ("Arthur Rackham", "Arthur Rackham's gnarled fairy-tale ink and watercolour, twisting trees with faces"),
    ("Bilibin", "Ivan Bilibin's Russian fairy-tale plates, ornamented borders and flat folk pageantry"),
    ("Kay Nielsen", "Kay Nielsen's Art Nouveau fairy-tale illustrations, elegant silhouettes, gilded patterning and icy jewel tones"),
    ("Edmund Dulac", "Edmund Dulac's jewel-toned fairy-tale plates, velvet midnight blues and delicate pattern"),
    ("Tove Jansson", "Tove Jansson's Moomin ink illustrations, soft rounded creatures and lonely Nordic horizons"),
    ("Beatrix Potter", "Beatrix Potter's watercolour vignettes, waistcoated animals in soft Lakeland light"),
    ("Quentin Blake", "Quentin Blake's scratchy pen-and-wash figures, gleeful wobbly energy"),
    ("Ronald Searle", "Ronald Searle's spidery satirical ink, crumbling institutions and magnificent cross-hatched chaos"),
    ("Heath Robinson", "Heath Robinson's absurd contraption illustrations, pulleys, string and deadpan Edwardian engineering"),
    ("Edward Gorey", "Edward Gorey's gothic pen-and-ink illustration, crosshatched shadows and macabre Victorian whimsy"),
    ("Shrigley", "David Shrigley's deadpan crude drawings, wonky black outlines and blunt humour"),
    ("Ralph Steadman", "Ralph Steadman's splattered gonzo ink, flailing caricatures and furious blots"),
    ("Dave McKean", "Dave McKean's layered mixed-media collage, photographic fragments and scratched paint"),
    ("Escher", "M.C. Escher's impossible lithographs, interlocking tessellations and looping staircases"),

    # ------------------------------------------------------------------
    # Photography
    # ------------------------------------------------------------------
    ("Muybridge", "Eadweard Muybridge's motion-study grids, sequential silhouettes against measured backdrops"),
    ("daguerreotype", "daguerreotype portraiture, silvered plates, stiff poses and a haunting mirror sheen"),
    ("wet-plate collodion", "wet-plate collodion portraits, scratched emulsion, pale eyes and chemical vignettes"),
    ("autochrome", "early autochrome colour photography, pointillist grain and faded Edwardian gardens"),
    ("Anna Atkins", "Anna Atkins's cyanotype botanicals, ghost-white algae on Prussian blue"),
    ("Blossfeldt", "Karl Blossfeldt's botanical close-ups, sculptural seed-heads in grey studio light"),
    ("Man Ray", "Man Ray's rayographs, ghostly white objects floating on photographic black"),
    ("Moholy-Nagy", "László Moholy-Nagy's Bauhaus photograms, stark geometry and experimental light-play"),
    ("Brassaï", "Brassaï's nocturnal Paris photographs, wet cobbles, fog haloes and gaslight"),
    ("Weegee", "Weegee's harsh flashbulb street photography, night-time crowds caught mid-gasp"),
    ("Lartigue", "Jacques Henri Lartigue's exuberant early snapshots, leaping figures and veiled motorists mid-blur"),
    ("Ansel Adams", "Ansel Adams's zone-system landscapes, thunderous monochrome peaks and crystalline detail"),
    ("Imogen Cunningham", "Imogen Cunningham's botanical modernism, magnolia geometry in silver gradients"),
    ("Dorothea Lange", "Dorothea Lange's FSA documentary photography, stark Dust Bowl faces and empathetic natural light"),
    ("Gordon Parks", "Gordon Parks's Life magazine photo essays, humanist realism and dramatic available light"),
    ("Helen Levitt", "Helen Levitt's colour street photography, candid urban children and saturated Kodachrome warmth"),
    ("Vivian Maier", "Vivian Maier's square-format street portraits, shop-window reflections and sidelong glances"),
    ("Saul Leiter", "Saul Leiter's fogged-window street photography, muted Kodachrome colour, umbrellas and cropped serendipity"),
    ("Fan Ho", "Fan Ho's 1950s Hong Kong photographs, smoky shafts of light and lone silhouettes"),
    ("Daido Moriyama", "Daido Moriyama's grainy high-contrast street photographs, blurred dogs and neon alleys"),
    ("Eggleston", "William Eggleston's deadpan Southern colour photography, saturated banality and parked cars"),
    ("Martin Parr", "Martin Parr's lurid seaside satire, ring-flash colour and chips in the rain"),
    ("Slim Aarons", "Slim Aarons's poolside leisure photography, pastel villas and impossible sunshine"),
    ("Edgerton", "Harold Edgerton's strobe photographs, milk-drop coronets and motion frozen mid-flight"),
    ("Sugimoto", "Hiroshi Sugimoto's long-exposure seascapes, a horizon bisecting silvered calm"),
    ("Crewdson", "Gregory Crewdson's staged suburban twilight, cinematic unease and sodium glow"),
    ("Burtynsky", "Edward Burtynsky's industrial-landscape photography, terraced mines and vast patterned scars"),
    ("Berenice Abbott", "Berenice Abbott's 1930s New York architectural photography, crisp shadows and towering urban geometry"),

    # ------------------------------------------------------------------
    # Cinema and animation
    # ------------------------------------------------------------------
    ("German Expressionist cinema", "German Expressionist cinema, painted shadows, tilted sets and kohl-eyed sleepwalkers"),
    ("film noir", "1940s film noir, venetian-blind shadows, cigarette smoke and rain-lacquered streets"),
    ("Douglas Sirk", "Douglas Sirk Technicolor melodrama, saturated interiors and immaculate suburban anguish"),
    ("Powell and Pressburger", "Powell and Pressburger Technicolor fantasia, painted skies and feverish saturated romance"),
    ("Tarkovsky", "Andrei Tarkovsky's sepia-toned long-take cinema, misty landscapes and spiritual ruin"),
    ("Parajanov", "Sergei Parajanov's tableau cinema, static frames stacked with folk costume and ritual objects"),
    ("Wong Kar-wai", "Wong Kar-wai's neon-soaked cinematography, smeared motion, rain and longing"),
    ("Kubrick", "Kubrick's one-point-perspective cinematography, clinical symmetry and impassive corridors"),
    ("Norstein", "Yuri Norstein's Soviet paper animation, misty layered cut-outs and lantern glow"),
    ("Lotte Reiniger", "Lotte Reiniger's silhouette animation, intricate black paper cutouts and luminous fairy-tale backdrops"),
    ("Švankmajer", "Jan Švankmajer's surreal stop-motion, antique drawers, bone and twitching clay"),
    ("Brothers Quay", "the Brothers Quay's dusty miniature stop-motion, cracked porcelain dolls and murky amber light"),
    ("Harryhausen", "Ray Harryhausen's stop-motion fantasy miniatures, tactile creatures and theatrical rear-projection lighting"),
    ("Laika", "Laika studio stop-motion, hand-sculpted puppets, moody sets and visible fingerprints"),
    ("Fleischer", "1930s Fleischer rubber-hose animation, wobbly grinning objects and bouncing rhythm"),
    ("UPA", "UPA mid-century limited animation, flat stylised backgrounds and jaunty modernist shorthand"),
    ("Chuck Jones", "Chuck Jones character animation, expressive silhouettes, desert mesas and immaculate timing"),
    ("Eyvind Earle", "Eyvind Earle's angular midcentury animation backgrounds, graphic forests and jewel-toned medieval silhouettes"),
    ("Mary Blair", "Mary Blair's mid-century Disney concept art, bold gouache shapes and whimsical colour harmonies"),
    ("Tartakovsky", "Genndy Tartakovsky's flat graphic action animation, stark silhouettes and bold speed-lines"),
    ("René Laloux", "René Laloux's Fantastic Planet animation, blue giants and stippled alien flora"),

    # ------------------------------------------------------------------
    # Comics and manga
    # ------------------------------------------------------------------
    ("Moebius", "Moebius's clean-line science fiction comics, pastel deserts and intricate biomechanical vistas"),
    ("Amano", "Yoshitaka Amano's ethereal fantasy illustration, wispy ink lines and opalescent watercolour elegance"),
    ("Katsuhiro Otomo", "Katsuhiro Otomo's dense manga cityscapes, tangled cables and crumbling neo-Tokyo concrete"),
    ("Tezuka", "Osamu Tezuka's vintage manga, big-eyed expressive figures and kinetic panel energy"),
    ("Winsor McCay", "Winsor McCay's Little Nemo comics, art-nouveau dream architecture and tumbling beds"),
    ("Herriman", "George Herriman's Krazy Kat strips, shifting desert backdrops and poetic slapstick"),
    ("ligne claire", "Hergé's ligne claire comics, uniform line weight, flat colour and tidy adventure"),

    # ------------------------------------------------------------------
    # Video game aesthetics
    # ------------------------------------------------------------------
    ("low-poly", "PlayStation-era low-poly 3D, wobbly textures, hard edges and fogged draw distance"),
    ("16-bit pixel art", "16-bit pixel art, chunky sprites, parallax skies and dithered sunsets"),
    ("Game Boy", "original Game Boy graphics, four shades of murky green and chunky charm"),
    ("ZX Spectrum", "ZX Spectrum loading-screen art, eight clashing colours and heroic attribute-grid compromise"),
    ("vector arcade", "vector arcade graphics, glowing wireframe geometry on black phosphor"),
    ("Obra Dinn", "Return of the Obra Dinn's 1-bit rendering, stark dithered monochrome shading"),
    ("Monument Valley", "Monument Valley's pastel isometric architecture, impossible stairways and quiet totem geometry"),
    ("Ōkami", "Ōkami's sumi-e cel shading, calligraphic brushstrokes and blooming colour"),
    ("Hollow Knight", "Hollow Knight's inky hand-drawn gloom, delicate insect silhouettes and soft spotlighting"),
    ("Cuphead", "Cuphead's 1930s cartoon style, watercolour backgrounds and rubber-hose menace"),
    ("Kentucky Route Zero", "Kentucky Route Zero's flat theatrical vignettes, silhouetted figures in glowing stage light"),

    # ------------------------------------------------------------------
    # Graphic design, posters and print
    # ------------------------------------------------------------------
    ("Bauhaus graphic design", "Bauhaus graphic design, geometric type, primary accents and disciplined asymmetry"),
    ("Swiss International", "Swiss International typography, rigorous grids, sans-serif restraint and generous white space"),
    ("Push Pin", "Push Pin Studios illustration, chromatic gradients, playful outlines and pop-Victorian mash-up"),
    ("Fillmore psychedelic", "1960s Fillmore psychedelic posters, melting lettering and vibrating complementary colours"),
    ("Tadanori Yokoo", "Tadanori Yokoo's psychedelic 1960s posters, blazing gradients, pop collage and Japanese graphic iconography"),
    ("Cassandre", "Cassandre's Art Deco travel posters, monumental streamlined ships and airbrushed speed"),
    ("WPA poster", "WPA poster art, flat serene national-park vistas and confident screen-printed colour"),
    ("Penguin paperback", "mid-century Penguin paperback covers, tripartite grids and restrained typographic wit"),
    ("Blue Note", "Blue Note album covers, duotone photography, cropped musicians and jazzy type"),
    ("Saville", "Peter Saville's Factory Records sleeve design, austere grids, waveforms and enigmatic restraint"),
    ("Jamie Reid", "Jamie Reid's punk xerox collage, ransom-note lettering and torn flag graphics"),
    ("David Carson", "David Carson's 1990s grunge typography, overprinted distressed layouts and broken grids"),
    ("Saul Bass", "Saul Bass title-card graphics, bold paper-cut silhouettes and punchy midcentury colour fields"),
    ("Rodchenko", "Rodchenko's Constructivist photomontage, diagonal compositions and shouting typography"),
    ("dazzle camouflage", "Norman Wilkinson's dazzle camouflage naval painting, jagged monochrome geometry and fractured maritime silhouettes"),
    ("linocut", "bold linocut printmaking, gouged white lines and heavy ink blacks"),
    ("mezzotint", "mezzotint printmaking, velvety blacks scraped patiently towards light"),
    ("risograph", "risograph zine printing, fluorescent spot colours, grain and charming misregistration"),

    # ------------------------------------------------------------------
    # Sci-fi and fantasy illustration
    # ------------------------------------------------------------------
    ("Chris Foss", "Chris Foss's 1970s sci-fi paperback art, chequered megaships and airbrushed nebulae"),
    ("Roger Dean", "Roger Dean's prog-rock album landscapes, floating islands and bone-white arches"),
    ("Syd Mead", "Syd Mead's gouache futurism, gleaming megastructures and chrome optimism"),
    ("John Harris", "John Harris's atmospheric sci-fi paintings, colossal hulls looming through haze"),
    ("vaporwave", "vaporwave aesthetics, pink-teal gradients, marble busts and chequerboard sunsets"),

    # ------------------------------------------------------------------
    # Textiles, craft, design and decorative arts
    # ------------------------------------------------------------------
    ("William Morris", "William Morris wallpaper patterns, dense curling acanthus and medieval-revival flatness"),
    ("Anni Albers", "Anni Albers's Bauhaus weavings, gridded thread geometry and quiet woven rhythm"),
    ("Gee's Bend", "Gee's Bend quilts, improvised bold geometry in worn work-cloth colours"),
    ("Kente", "Kente cloth weaving, banded gold, green and crimson geometry"),
    ("boro", "Japanese boro textiles, indigo patchwork, sashiko stitches and mended generations"),
    ("Marimekko", "Marimekko print design, giant joyful poppies and flat Finnish colour"),
    ("Memphis Group", "Memphis Group design, squiggles, terrazzo, clashing pastels and 1980s irreverence"),
    ("googie", "googie atomic-age design, boomerang angles, starbursts and optimistic chrome"),
    ("Clarice Cliff", "Clarice Cliff's Art Deco ceramics, bold geometric hand-painted motifs and candy-coloured glaze"),
    ("Lalique", "René Lalique's Art Nouveau glasswork, opalescent translucency, flowing flora and delicate moulded relief"),
    ("Tiffany", "Tiffany stained glass, leaded dragonflies, wisteria and glowing opalescent colour"),
    ("Gaudí", "Gaudí's trencadís mosaic architecture, undulating broken-tile colour and bone-like curves"),
    ("Lucie Rie", "Lucie Rie's studio pottery, poised thin-walled bowls, sgraffito lines and volcanic glazes"),
    ("Erté", "Erté's Art Deco fashion plates, elongated silhouettes, metallic ornament and theatrical Parisian glamour"),
    ("Leon Bakst", "Leon Bakst's Ballets Russes costume designs, jewelled patterns and theatrical opulence"),
    ("Iznik", "Ottoman Iznik tiles, cobalt and coral tulips on white"),
    ("zellige", "Moroccan zellige tilework, hand-cut geometric mosaic stars"),
    ("Wedgwood", "Wedgwood jasperware relief, white classical figures on matte duck-egg blue"),
    ("Fabergé", "Fabergé goldsmithing, enamelled lattice, seed pearls and a jewelled surprise"),
    ("origami", "folded origami paper sculpture, crisp geometric creases and clean shadows"),

    # ------------------------------------------------------------------
    # Sculpture
    # ------------------------------------------------------------------
    ("Calder", "Alexander Calder's mobiles, balanced primary shapes drifting on wire"),
    ("Hepworth", "Barbara Hepworth's pierced sculptures, smooth ovoids, taut strings and coastal light"),
    ("Giacometti", "Giacometti's attenuated bronze figures, striding through vast empty space"),
]
