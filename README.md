ttfdiet
=======
**ttfdiet** (*TTF DIacritics Encoding Tool*) applies a “diet” to a .ttf font: it modernizes
the way in which glyphs for precomposed Unicode characters are stored in
a TrueType-flavored OpenType font, and reduces the font’s file size. 

Credits
-------
* by: [Karsten Lücke](./AUTHORS) and [Adam Twardoch](./AUTHORS) 
* homepage: http://github.com/twardoch/ttfdiet

Disclaimer
----------
The tool is **EXPERIMENTAL**, a proof-of-concept, and is intended for experienced 
font developers.

The tool is intended to create fonts that:

* demonstrate the file size reduction that can be achieved by
  an optimization method similar to the one used by the tool,
* test the level of applications’ basic OTL support, most notably for
  “ccmp” decomposition and “mark”/“mkmk” attachment. To test OTL support,
  install a dieted font and type a precomposed character such “Ä”, “á”, etc.

This tool is **NOT** intended to produce shipping-quality fonts.

Requirements
------------
1. The tool requires Python 2.6 or newer and the fontTools/TTX package from:
   https://github.com/behdad/fonttools/
2. inputfont must be a TrueType-flavored (.ttf) fonts that contains
   a “glyf” table. It does NOT work with CFF-flavored .otf fonts.
3. inputfont should contain a “GSUB” table.
4. inputfont should contain combining marks (U+03xx) which should be assigned
   to the mark class (3) in the “GDEF” table.
5. inputfont should contain a “mark” GPOS feature that positions the combining
   mark glyphs over base glyphs.
6. ot-sanitise from https://github.com/khaledhosny/ots is recommended.

Main functionality (“diet”)
---------------------------
The tool applies a “diet” to a .ttf font — it optimizes how precomposed 
Unicode characters such as “Ä” are expressed in the internal font structures
of a TrueType-flavored OpenType font. The diet reduces the size of the font, 
and also eliminates certain redundant and ambiguous information in the font. 

The diet consists of the following steps:

1. It “blanks” all glyphs that, in the “cmap” table, represent precomposed
   Unicode characters (such as U+00E1, LATIN SMALL LETTER A WITH ACUTE),
   i.e. it removes all contours and components for those glyphs from the
   “glyf” table. Note: the tool cannot process the “CFF” table. Also note 
   that the glyphs are “blanked” but not deleted, as their presence is 
   required by the font’s “cmap” table. 
3. It deletes kerning pairs in the “GPOS” “kern” feature that involve 
   any glyphs which have been “blanked” in the first step. 
3. It adds a “GSUB” lookup that substitutes every glyph that represents
   a precomposed Unicode character with a sequence of glyphs that represent
   the Unicode canonical decomposition of that precomposed character,
   and adds the lookup to the “ccmp” feature.

The typical size reduction of a multilingual font is 5–10%.

Optionally, the tool attempts to run OTS (ot-sanitise) on the outputfont. 
OTS is an open-source tool used by web browsers to verify web fonts before 
they are displayed. If the ot-sanitise test fails, the font may not reliably 
work in web browsers.

Limitations
-----------
* The tool assumes that the OpenType Layout engine which will use the font will 
  “do the right thing”, i.e. apply the OpenType “ccmp”, “mark” and “mkmk” features 
  during the text layout. Unfortunately, some apps, most notably Microsoft Word 
  and the Adobe CC apps, don’t quite do that, so **the dieted fonts won’t perform 
  in these apps as expected**. 
* The tool currently only deletes unneeded kerning pairs from “GPOS” PairPos 
  Format 1 subtables (single glyph pairs, typically used for “exception kerning”). 
  The tool currently does not in any way process “GPOS” PairPos Format 2 subtables, 
  used for “class kerning”. Also, it does not add any contextual kerning. 
* The tool does not process the legacy TrueType “kern” table. 

Usage
-----
```
Usage: python ttfdiet.py [options] inputfont.ttf [outputfont.ttf]

The tool has a number of options, which are listed below.
To enable an option, specify it with the value 1.
To disable an option, specify it with the value 0.
Not specified options will use the default values shown below.

Options:
  --version             show program's version number and exit
  -h, --help            show this help message and exit
  -v 1, --verbose=1     print additional information during processing

  File handling:
    -f 0, --fea=0       save 'ccmp' feature in AFDKO-syntax .fea file
    -S 0, --sanitise=0  1: test outputfont with 'ot-sanitise'; 2: also remove
                        outputfont if test fails

  Core diet options:
    -g 1, --glyf=1      remove components and contours from precomposed glyphs
    -k 1, --kern=1      remove precomposed glyphs from 'GPOS' kern
                        PairPosFormat1 subtables
    -C 1, --ccmp=1      add 'ccmp' subtable that decomposes precomposed glyphs
    -s list, --skipmarks=list
                        do not process precomposed glyphs involving these
                        marks; default list is
                        031B,0321,0322,0334,0335,0336,0337,0338
    -a 0, --repmarks=0  report marks missing in font that would allow a better
                        diet

  Additional diet options:
    -c 1, --cmap=1      remove all 'cmap' subtables except Windows-platform
    -n 1, --name=1      remove all 'name' records except Windows-platform
    -p 1, --post=1      remove 'post' glyph names

  Various options:
    -r 1, --rename=1    add 'Diet' prefix to 'name' records (also enables
                        --name)
    -d 0, --dsig=0      add empty 'DSIG' table

```
Examples
--------

The [examples](./examples/) folder contains the original font *DroidSerif-Regular.ttf* (v1.03, size: 248,904 bytes), and the dieted font *DroidSerif-Regular.diet.ttf* (size: 224,000 bytes). In this case, the diet efficiency is 10%. The typical size reduction for multilingual .ttf fonts will be about 5–10%. 

```
$ ./ttfdiet.py examples/DroidSerif-Regular.ttf
Skipping marks with codepoints 031B 0321 0322 0334 0335 0336 0337 0338.
Dieting DroidSerif-Regular.ttf...
'GDEF' table's GlyphClassDef doesn't flag glyph 'uni0487' as mark. Corrected.
'GDEF' table's GlyphClassDef doesn't flag glyph 'uni20F0' as mark. Corrected.
Saving examples/DroidSerif-Regular.diet.ttf...
Diet efficiency: 10.0% (from 248904 to 224000 bytes)
Done.
```
Software License
----------------
Licensed under the [Apache License, Version 2.0](http://www.apache.org/licenses/LICENSE-2.0)
