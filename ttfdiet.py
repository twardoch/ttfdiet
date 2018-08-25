#!/usr/bin/env python
# -*- coding: utf-8 -*-

# ttfdiet v0.806 -- TTF DIacritics Encoding Tool

# Copyright 2014 Karsten Lücke
# Copyright 2014 Adam Twardoch
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# CHANGELOG: 
#  2018-06-29 v0.807 davelab6: Minor tweak to update ots-sanitize and version number
#  2017-10-07 v0.806 Adam: Minor tweak
#  2016-11-25 v0.803 Adam: Minor tweaks with filesystem handling
#  2014-12-19 v0.802 Adam: minor tweaks
#  2014-12-18 v0.801 Adam: Rewritten usage and help, added -v option and ability to specify output file
#  2014-06-28 v0.705 Karsten: switching to optparse, allow ignoring mark codepoints, output list of missing mark codepoints
#  2014-06-26 v0.704 Karsten: identifying mark glyphs via mark/mkmk lookups, adding ot-sanitise validation if available
#  2014-06-26 v0.703 Karsten: refined conditions for applying decomposition, shape deletion
#  2014-06-26 v0.702 Karsten: test font checks that GDEF ClassDef for mark glyphs is 3
#  2014-06-25 v0.701 Karsten: test font, add ccmp to gsub, add Dummy DSIG, remove contours/components, kerning from gpos ppf1, win name records, win cmap subtables, post glyphnames
#  2014-06-20 v0.700 Adam: decomposition rule via cmap+unicodedata to afdko-syntax .fea file


# This is a testing tool. This is NOT a font production tool!
# Test fonts created are not meant to be distributed.
#
#
#########################################################################################################

import sys
import os
import os.path
try: 
	import unicodedata2 as unicodedata
except ImportError: 
	import unicodedata
from copy import deepcopy
from struct import pack
from subprocess import Popen,PIPE
import optparse

try:
	from fontTools.ttLib import TTFont, TTLibError, newTable
	from fontTools.ttLib.tables.otTables import *
except: 
	print "Install https://github.com/behdad/fonttools/archive/master.zip" 
	sys.exit(1)

try: set
except NameError: from sets import Set as set
def cleanUpList(l):
	ll = list( set(l))
	ll.sort()
	return ll
def strictSets(class1,class2): return list( set(class1) & set(class2) )
def minusSets( class1,class2): return list( set(class1) - set(class2) )

#########################################################################################################

TOOL_URL = "https://github.com/twardoch/ttfdiet"
TOOL_VERSION = "0.807"
VERBOSE                           = 1
REMOVE_PRECOMPOSED_OUTLINES       = 1
REMOVE_PRECOMPOSED_FROM_GPOS_KERN = 1
REMOVE_ALL_BUT_WIN_CMAP_SUBTABLES = 1
REMOVE_ALL_BUT_WIN_NAME_RECORDS   = 1
REMOVE_POST_GLYPHNAMES            = 1

DECOMPOSE_PRECOMPOSED_IN_CCMP     = 1
SAVE_FEA_FILE                     = 0

RENAME_FONT                       = 1
RENAME_FONT_ADDITION              = u"Diet"
DEFAULT_OUTPATH_ADDITION          = u".diet"

REPORT_MISSING_MARKS              = 1
CORRECT_MARK_CLASS                = 1
SKIP_MARKS                        = u"031B,0338" # you may not want to decompose precomposed ones that involve horn or overstruck long solidus
SKIP_MARKS_FINAL                  = None

ADD_DUMMY_DSIG                    = 0

OTS_SANITISE                      = 0
OTS_PATH_OR_COMMAND               = "ots-sanitize" # this expects that the ot-sanitise binary is present in a system-known bin folder

class NoWrapHelpFormatter(optparse.IndentedHelpFormatter):
 	def _formatter(self, text):
		return '\n'.join( [ s.rstrip() for s in text.split('\n') ] )
	def format_description(self, description):
		if description:
			return self._formatter(description) + "\n"
		else:
			return ""
	def format_epilog(self, epilog):
		if epilog:
			return "\n" + self._formatter(epilog) + "\n"
		else:
			return ""

def handleOptions():
	global TOOL_VERSION
	global TOOL_URL
	global VERBOSE
	global REMOVE_PRECOMPOSED_OUTLINES 
	global REMOVE_PRECOMPOSED_FROM_GPOS_KERN 
	global REMOVE_ALL_BUT_WIN_CMAP_SUBTABLES 
	global REMOVE_ALL_BUT_WIN_NAME_RECORDS 
	global REMOVE_POST_GLYPHNAMES 

	global DECOMPOSE_PRECOMPOSED_IN_CCMP 
	global SAVE_FEA_FILE 

	global RENAME_FONT 
	global RENAME_FONT_ADDITION

	global REPORT_MISSING_MARKS 
	global SKIP_MARKS 
	global SKIP_MARKS_FINAL 

	global ADD_DUMMY_DSIG 

	global OTS_SANITISE 
	global OTS_PATH_OR_COMMAND 

	# parse argv:
	parser = optparse.OptionParser(formatter=NoWrapHelpFormatter(), 
		usage=u"usage: python %prog [options] inputfont.ttf [outputfont.ttf]", 
		version=u"%prog v" + TOOL_VERSION)

	parser.description = u"""%prog v""" + TOOL_VERSION + u"""
==========
'TTF DIacritics Encoding Tool' applies a diet to a .ttf font: it modernizes 
the way in which glyphs for precomposed Unicode characters are stored in 
a TrueType-flavored OpenType font, and reduces the font's file size. 

Disclaimer
----------
The tool is EXPERIMENTAL and intended for experienced font developers.  

It is intended to create fonts that:  

* demonstrate the file size reduction that can be achieved by  
  an optimization method similar to the one used by the tool,
* test the level of applications' basic OTL support, most notably for 
  'ccmp' decomposition and 'mark'/'mkmk' attachment. To test OTL support, 
  install a dieted font and type a precomposed character such "Ä", "á", etc.

This tool is NOT intended to produce shipping-quality fonts. 

Requirements
------------
1. The tool requires Python 2.6 or newer and the fontTools/TTX package from:
   https://github.com/behdad/fonttools/
2. inputfont must be a TrueType-flavored (.ttf) fonts that contains
   a 'glyf' table. It does NOT work with CFF-flavored .otf fonts.
3. inputfont should contain a 'GSUB' table.
4. inputfont should contain combining marks (U+03xx) which should be assigned
   to the mark class (3) in the 'GDEF' table.
5. inputfont should contain a 'mark' GPOS feature that positions the combining
   mark glyphs over base glyphs.
6. ot-sanitise from https://github.com/khaledhosny/ots is recommended.

Diet
----
The tool applies a 'diet' to a .ttf font. The diet consists of two steps:

1. It 'blanks' all glyphs that, in the 'cmap' table, represent precomposed
   Unicode characters (such as U+00E1, LATIN SMALL LETTER A WITH ACUTE),
   i.e. it removes all contours and components for those glyphs from the
   'glyf' table (note: the tool cannot process the 'CFF' table).
2. It adds a 'GSUB' lookup that substitutes every glyph that represents
   a precomposed Unicode character with a sequence of glyphs that represent
   the Unicode canonical decomposition of that precomposed character,
   and adds the lookup to the 'ccmp' feature.

The typical size reduction of a multilingual font is 5–10%.

Optionally, the tool attempts to run OTS (ot-sanitise) on the outputfont. 
OTS is an open-source tool used by web browsers to verify web fonts before 
they are displayed. If the ot-sanitise test fails, the font may not reliably 
work in web browsers.

Options
-------
The tool has a number of options, which are listed below.  
To enable an option, specify it with the value 1. 
To disable an option, specify it with the value 0. 
Not specified options will use the default values shown below.""" 

	parser.add_option("-v", "--verbose", 
		help=u"print additional information during processing", 
		default=VERBOSE, 
		metavar=str(VERBOSE), 
		nargs=1 )
	group = optparse.OptionGroup(parser, u"File handling")
	group.add_option("-f", "--fea", 
		help=u"save 'ccmp' feature in AFDKO-syntax .fea file", 
		default=SAVE_FEA_FILE, 
		metavar=str(SAVE_FEA_FILE), 
		nargs=1 )
	group.add_option("-S", "--sanitise", 
		help=u"1: test outputfont with 'ot-sanitise'; 2: also remove outputfont if test fails ", 
		default=OTS_SANITISE, 
		metavar=str(OTS_SANITISE), 
		nargs=1 )
	parser.add_option_group(group)
	group = optparse.OptionGroup(parser, u"Core diet options")
	group.add_option("-g", "--glyf", 
		help=u"remove components and contours from precomposed glyphs", 
		default=REMOVE_PRECOMPOSED_OUTLINES, 
		metavar=str(REMOVE_PRECOMPOSED_OUTLINES), 
		nargs=1 )
	group.add_option("-k", "--kern", 
		help=u"remove precomposed glyphs from 'GPOS' kern PairPosFormat1 subtables", 
		default=REMOVE_PRECOMPOSED_FROM_GPOS_KERN, 
		metavar=str(REMOVE_PRECOMPOSED_FROM_GPOS_KERN), 
		nargs=1 )
	group.add_option("-C", "--ccmp", 
		help=u"add 'ccmp' subtable that decomposes precomposed glyphs", 
		default=DECOMPOSE_PRECOMPOSED_IN_CCMP, 
		metavar=str(DECOMPOSE_PRECOMPOSED_IN_CCMP), 
		nargs=1 )
	group.add_option("-s", "--skipmarks", 
		help=u"do not process precomposed glyphs involving these marks; default list is %s" % (SKIP_MARKS), 
		default=SKIP_MARKS, 
		metavar=str("list"), 
		nargs=1 )
	group.add_option("-a", "--repmarks", 
		help=u"report marks missing in font that would allow a better diet", 
		default=OTS_SANITISE, 
		metavar=str(OTS_SANITISE), 
		nargs=1 )
	parser.add_option_group(group)
	group = optparse.OptionGroup(parser, u"Additional diet options")
	group.add_option("-c", "--cmap", 
		help=u"remove all 'cmap' subtables except Windows-platform", 
		default=REMOVE_ALL_BUT_WIN_CMAP_SUBTABLES, 
		metavar=str(REMOVE_ALL_BUT_WIN_CMAP_SUBTABLES), 
		nargs=1 )
	group.add_option("-n", "--name", 
		help=u"remove all 'name' records except Windows-platform", 
		default=REMOVE_ALL_BUT_WIN_NAME_RECORDS, 
		metavar=str(REMOVE_ALL_BUT_WIN_NAME_RECORDS), 
		nargs=1 )
	group.add_option("-p", "--post", 
		help=u"remove 'post' glyph names", 
		default=REMOVE_POST_GLYPHNAMES, 
		metavar=str(REMOVE_POST_GLYPHNAMES), 
		nargs=1 )
	parser.add_option_group(group)
	group = optparse.OptionGroup(parser, u"Various options")
	group.add_option("-r", "--rename", 
		help=u"add '%s' prefix to 'name' records (also enables --name)" % RENAME_FONT_ADDITION, 
		default=RENAME_FONT, 
		metavar=str(RENAME_FONT), 
		nargs=1 )
	group.add_option("-d", "--dsig", 
		help=u"add empty 'DSIG' table", 
		default=ADD_DUMMY_DSIG, 
		metavar=str(ADD_DUMMY_DSIG), 
		nargs=1 )
	parser.add_option_group(group)

	parser.epilog = u"""License
-------
This tool is open-source under the Apache 2 license, and is available from:
%s """ % (TOOL_URL)

	options, args = parser.parse_args()

	# reset options:
	VERBOSE                             = int( options.__dict__["verbose"     ] )
	REMOVE_PRECOMPOSED_OUTLINES         = int( options.__dict__["glyf"        ] )
	REMOVE_PRECOMPOSED_FROM_GPOS_KERN   = int( options.__dict__["kern"        ] )
	REMOVE_ALL_BUT_WIN_CMAP_SUBTABLES   = int( options.__dict__["cmap"        ] )
	REMOVE_ALL_BUT_WIN_NAME_RECORDS     = int( options.__dict__["name"        ] )
	REMOVE_POST_GLYPHNAMES              = int( options.__dict__["post"        ] )

	DECOMPOSE_PRECOMPOSED_IN_CCMP       = int( options.__dict__["ccmp"        ] )
	SAVE_FEA_FILE                       = int( options.__dict__["fea"         ] )

	renameFont                          =      options.__dict__["rename"      ]
	try:
		# integer means: do it, and use predefined default
		RENAME_FONT                     = int(renameFont)
	except:
		# non-integer i.e. string means: do it, with the string provided
		RENAME_FONT                     = 1
		RENAME_FONT_ADDITION            = str(renameFont)
	if RENAME_FONT:
		REMOVE_ALL_BUT_WIN_NAME_RECORDS = 1

	REPORT_MISSING_MARKS                = int( options.__dict__["repmarks"    ] )
	skipMarks                           =      options.__dict__["skipmarks"   ]
	skipMarksAddkToDefault              = "+" in skipMarks
	skipMarks                           = skipMarks.replace("+","")
	try:
		# integer means: 
		# a) don't skip any marks
		# b) skip all marks
		# c) a hex codepoint was misunderstood as being an integer, do as d)
		skipInt = int(skipMarks)
		if skipInt == 0: # process all marks (including default skip marks)
				SKIP_MARKS_FINAL = ""
		elif skipInt == 1: # skip all marks (including default skip marks)
				SKIP_MARKS_FINAL = deepcopy(SKIP_MARKS)
		else: # a single mark hex codepoint that int() unfortunately accepts, do as d)
			if skipMarksAddkToDefault:
				SKIP_MARKS_FINAL = "%s,%s" % (skipMarks,SKIP_MARKS)
			else:
				SKIP_MARKS_FINAL =            skipMarks
	except:
		# d) skip marks as defined by hex codepoints
			if skipMarksAddkToDefault:
				SKIP_MARKS_FINAL = "%s,%s" % (skipMarks,SKIP_MARKS)
			else:
				SKIP_MARKS_FINAL =            skipMarks
	SKIP_MARKS_FINAL = SKIP_MARKS_FINAL.strip().replace(","," ").replace(";"," ").replace("-"," ").replace("/"," ").split()
	SKIP_MARKS_FINAL = cleanUpList(SKIP_MARKS_FINAL)
	SKIP_MARKS_FINAL.sort()
	if len(SKIP_MARKS_FINAL) == 1:
		if VERBOSE: print "Skipping mark with codepoint %s."   % " ".join(SKIP_MARKS_FINAL)
	elif SKIP_MARKS_FINAL:
		if VERBOSE: print "Skipping marks with codepoints %s." % " ".join(SKIP_MARKS_FINAL)
	SKIP_MARKS_FINAL = [int(m, 16) for m in SKIP_MARKS_FINAL if len(m) ] ; m=None

	ADD_DUMMY_DSIG                      = int( options.__dict__["dsig"        ] )

	OTS_SANITISE            = int( options.__dict__["sanitise"    ] )

	# return file names:
	if len(args) < 1: 
		print "Please specify an inputfont."
		sys.exit(2)
	elif len(args) < 2: 
		inPath = args[0]
		outPath = os.path.splitext(inPath)[0] + DEFAULT_OUTPATH_ADDITION.lower().strip() + os.path.splitext(inPath)[1]
	else: 
		inPath = args[0]
		outPath = args[1]
	return inPath, outPath

#########################################################################################################

MARK_GLYPH_CODEPOINT_RANGE = [ int(m) for m in range(65000) if unicodedata.category(unichr(m)) == "Mn" ]; m=None # also allow for "M"?
MARK_GLYPH_CODEPOINT_RANGE.remove(int("034F", 16))

PPF2_SUPPORTED = 0 # not tested yet! and deactivated ...

#########################################################################################################

def saveFile(data,file):
	modus = "wb"
	file = os.path.abspath(file)
	if os.path.exists(file): os.remove(file)
	directory = os.path.dirname(file)
	if not os.path.exists(directory): os.makedirs(directory)
	theFile = open(file,modus)
	theFile.write(data)
	theFile.close()

def unicodeIntToHexstr(intUnicode):
	hexUnicode = "%X".lstrip("0x") % intUnicode
	return "0"*(4-len(hexUnicode)) + hexUnicode

#########################################################################################################

def testFont(ttx,umap,nmap,markGlyphs):
	fontIsFine = 1
	# are mark glyphs there?
	codes = umap.keys()
	marksFound = len(strictSets(MARK_GLYPH_CODEPOINT_RANGE,codes))
	if not marksFound:
				if VERBOSE: print "Mark table glyphs missing."
				fontIsFine = 0			
	# is GSUB there? (Won't create one yet.)
	if "GSUB" not in ttx:
				fontIsFine = 0
				if VERBOSE: print "'GSUB' table missing."
	# is GPOS there and is mark feature there?
	if "GPOS" not in ttx:
				fontIsFine = 0
				if VERBOSE: print "'GPOS' table missing."
	else:
		markThere = 0	
		for r in ttx["GPOS"].table.FeatureList.FeatureRecord:
			if r.FeatureTag == "mark":
				markThere = 1
		if not markThere:
				fontIsFine = 0
				if VERBOSE: print "'GPOS' table misses 'mark' feature."
	# is GDEF there and are marks classified as mark glyphs?
	if "GDEF" not in ttx:
				fontIsFine = 0
				if VERBOSE: print "'GDEF' table missing."
	else:
		try:
				classdefs = ttx["GDEF"].table.GlyphClassDef.classDefs
		except:
				classdefs = 0
				fontIsFine = 0
				if VERBOSE: print "'GDEF' table misses GlyphClassDef."
		if classdefs:
			# by unicode codepoint:
			for n in nmap:
				if n in classdefs:
					isMark = 0
					for uuu in nmap[n]:
						if uuu in MARK_GLYPH_CODEPOINT_RANGE:
							isMark = 1
					if isMark:
						if n in classdefs:
							if classdefs[n] != 3 and CORRECT_MARK_CLASS:
								classdefs[n] = 3
								if VERBOSE: print "'GDEF' table's GlyphClassDef doesn't flag glyph '%s' as mark. Corrected." % n
						else:
							# do that anyway ...
								classdefs[n] = 3
								if VERBOSE: print "'GDEF' table's GlyphClassDef doesn't contain mark glyph '%s'. Added." % n
			n=None
			# by actual use in mark, mkmk, liga-mark lookups:
			for n in markGlyphs:
						if n in classdefs:
							if classdefs[n] != 3 and CORRECT_MARK_CLASS:
								classdefs[n] = 3
								if VERBOSE: print "'GDEF' table's GlyphClassDef doesn't flag glyph '%s' as mark. Corrected." % n
						else:
							# do that anyway ...
								classdefs[n] = 3
								if VERBOSE: print "'GDEF' table's GlyphClassDef doesn't contain mark glyph '%s'. Added." % n
	# report:
	return fontIsFine

def getMarkGlyphs(ttx):
	if "GPOS" not in ttx:
		return []
	lookupIndices = []
	for r in ttx["GPOS"].table.FeatureList.FeatureRecord:
		if r.FeatureTag in ["mark","mkmk"]:
			for l in r.Feature.LookupListIndex:
				if l not in lookupIndices:
					lookupIndices += [int( l )]
#	print "lookupIndices",lookupIndices
	marks = []
	for lIdx in lookupIndices:
		lookup = ttx["GPOS"].table.LookupList.Lookup[lIdx]
#		print lookup.LookupType
		if lookup.LookupType in [4,5]:
#			print dir(lookup)
			for s in lookup.SubTable:
				if lookup.LookupType in [4,5]:
					subtable = s
				elif lookup.LookupType == 9 and s.ExtensionLookupType in [4,5]:
					subtable = s.ExtSubTable
				else:
					continue
				marks += subtable.MarkCoverage.glyphs
		elif lookup.LookupType == 6:
#			print dir(lookup)
			for s in lookup.SubTable:
				if lookup.LookupType == 6:
					subtable = s
				elif lookup.LookupType == 9 and s.ExtensionLookupType == 6:
					subtable = s.ExtSubTable
				else:
					continue
				marks += subtable.Mark1Coverage.glyphs
				marks += subtable.Mark2Coverage.glyphs
	marks = cleanUpList(marks)
	return marks

def removeOutlines(ttx,glyphs_removeOutlinesAndInstructions):
	# remove contours and components:
	if "glyf" not in ttx:
		if VERBOSE: print "This is not a 'glyf' based font. Won't remove contours/components."
		return
	if not glyphs_removeOutlinesAndInstructions:
		return
	glyphs = ttx["glyf"].glyphs
	for n in glyphs_removeOutlinesAndInstructions:
		glyphs[n].data = ""
	# set LSB = 0:
	if not glyphs_removeOutlinesAndInstructions:
		return
	for glyphname in ttx["hmtx"].metrics: # this is a dict!
		if glyphname in glyphs_removeOutlinesAndInstructions:
			try: 
				ttx["hmtx"].metrics[glyphname][1] = 0
			except: 
				pass

def renameFont(ttx):
	# string is prepared only for Win platform name strings ...
	space         = "".join([ pack(">"+"H",ord(char)) for char in                                                    " " ]) ; char=None
	renameWith    = "".join([ pack(">"+"H",ord(char)) for char in RENAME_FONT_ADDITION.strip().strip("'").strip('"')+" " ]) ; char=None
	renameWithout = "".join([ pack(">"+"H",ord(char)) for char in RENAME_FONT_ADDITION.strip().strip("'").strip('"')     ]) ; char=None
	# check font names:
#	id1 = ""
#	id4 = ""
#	id6 = ""
#	for nIdx in range(len(ttx["name"].names)-1,-1,-1):
#		if   ttx["name"].names[nIdx].nameID == 4:
#			id4 = deepcopy(ttx["name"].names[nIdx].string)
#		elif ttx["name"].names[nIdx].nameID == 6:
#			id6 = deepcopy(ttx["name"].names[nIdx].string)
#		elif ttx["name"].names[nIdx].nameID == 1:
#			id1 = deepcopy(ttx["name"].names[nIdx].string)
	# strings with and without spaces:
	namesWithSpaces    = [1,16,21, 3, 4,18]
	namesWithoutSpaces = [6, 20]
	# adjust font names:
	for nIdx in range(len(ttx["name"].names)-1,-1,-1):
		if   ttx["name"].names[nIdx].nameID in namesWithSpaces: # addition with space
			ttx["name"].names[nIdx].string = renameWith    + ttx["name"].names[nIdx].string
		elif ttx["name"].names[nIdx].nameID in namesWithoutSpaces: # addition without space
			ttx["name"].names[nIdx].string = renameWithout + ttx["name"].names[nIdx].string
	# I add space before the name so all testfonts
	# can be found in one range in font menus ...

def removeAllButWinNameRecords(ttx):
	for nIdx in range(len(ttx["name"].names)-1,-1,-1):
		if ttx["name"].names[nIdx].platformID != 3:
			del ttx["name"].names[nIdx]
	
def removeAllButWinCmapSubtable(ttx):
	for tIdx in range(len(ttx["cmap"].tables)-1,-1,-1):
		if ttx["cmap"].tables[tIdx].platformID != 3: # we only leave platform 3 in the font
			del ttx["cmap"].tables[tIdx]	

# continue here:
def removeGPOSkern(ttx,glyphs_removeOutlinesAndInstructions):
	if not glyphs_removeOutlinesAndInstructions:
		return
	lookupIndices = []
	for r in ttx["GPOS"].table.FeatureList.FeatureRecord:
		if r.FeatureTag == "kern":
			for l in r.Feature.LookupListIndex:
				if l not in lookupIndices:
					lookupIndices += [int( l )]
#	print "lookupIndices",lookupIndices
	for lIdx in lookupIndices:
		lookup = ttx["GPOS"].table.LookupList.Lookup[lIdx]
#		print lookup.LookupType
		if lookup.LookupType in [2,9]:
#			print dir(lookup)
			for s in lookup.SubTable:
				if lookup.LookupType == 2:
					subtable = s
				elif lookup.LookupType == 9 and s.ExtensionLookupType == 2:
					subtable = s.ExtSubTable
				else:
					continue
#				print "subtable",dir(subtable)
				if subtable.Format == 1:
#					print "ppf1"
					delPairSets = []
					# coverage table:
					for gIdx in range(len(subtable.Coverage.glyphs)-1,-1,-1):
						if subtable.Coverage.glyphs[gIdx] in glyphs_removeOutlinesAndInstructions:
							del subtable.Coverage.glyphs[gIdx]
							delPairSets += [int(gIdx)]
					# pair sets:
					for pIdx in range(len(subtable.PairSet)-1,-1,-1):
						if pIdx in delPairSets:
							del subtable.PairSet[pIdx]
						else:
							p = subtable.PairSet[pIdx]
							for pvIdx in range(len(p.PairValueRecord)-1,-1,-1):
								if p.PairValueRecord[pvIdx].SecondGlyph in glyphs_removeOutlinesAndInstructions:
									del p.PairValueRecord[pvIdx]
				elif subtable.Format == 2 and PPF2_SUPPORTED:
					# coverage table:
					for gIdx in range(len(subtable.Coverage.glyphs)-1,-1,-1):
						if subtable.Coverage.glyphs[gIdx] in glyphs_removeOutlinesAndInstructions:
							del subtable.Coverage.glyphs[gIdx]
					# class defs:
					class1Before = cleanUpList([ int(subtable.ClassDef1.classDefs[g]) for g in subtable.ClassDef1.classDefs ]+[0]) # includes 0
					class2Before = cleanUpList([ int(subtable.ClassDef2.classDefs[g]) for g in subtable.ClassDef2.classDefs ]+[0]) # includes 0
					glyphs1 = subtable.ClassDef1.classDefs.keys()
					class1glyphs = {}
					class2glyphs = {}
					for g1 in glyphs1:
						try:    class1glyphs[ subtable.ClassDef1.classDefs[g1] ] += [g1]
						except: class1glyphs[ subtable.ClassDef1.classDefs[g1] ]  = [g1]
						if g1 in glyphs_removeOutlinesAndInstructions:
							del subtable.ClassDef1.classDefs[g1]
					glyphs2 = subtable.ClassDef2.classDefs.keys()
					for g2 in glyphs2:
						try:    class2glyphs[ subtable.ClassDef2.classDefs[g2] ] += [g2]
						except: class2glyphs[ subtable.ClassDef2.classDefs[g2] ]  = [g2]
						if g2 in glyphs_removeOutlinesAndInstructions:
							del subtable.ClassDef2.classDefs[g2]
					class1After = cleanUpList([ int(subtable.ClassDef1.classDefs[g]) for g in subtable.ClassDef1.classDefs ]+[0]) # includes 0
					class2After = cleanUpList([ int(subtable.ClassDef2.classDefs[g]) for g in subtable.ClassDef2.classDefs ]+[0]) # includes 0
					if VERBOSE: print "class1glyphs",class1glyphs
					if VERBOSE: print "class2glyphs",class2glyphs
					# THE PART BELOW IS NOT TESTED YET:
					# class count:
					# (mind that deleting glyphs from classes
					# does not necessarily result in the class being deleted)
					correctClass1 = 0
					if subtable.Class1Count != len(class1After):
						correctClass1 = 1
						if VERBOSE: print "Deleted %s class1!" % (subtable.Class1Count-len(class1After))
						subtable.Class1Count = len(class1After)
					correctClass2 = 0
					if subtable.Class2Count != len(class2After):
						correctClass2 = 1
						if VERBOSE: print "Deleted %s class2!" % (subtable.Class2Count-len(class2After))
						subtable.Class2Count = len(class2After)
					# class records:
					for c1idx in range(len(subtable.Class1Record)-1,-1,-1):
						if c1idx not in class1After:
							del subtable.Class1Record[c1idx]
						else:
							for c2idx in range(len(subtable.Class1Record[c1idx].Class2Record)-1,-1,-1):
								if c2idx not in class2After:
									del subtable.Class1Record[c1idx].Class2Record[c2idx]
					# adjust class defs:
					if VERBOSE: print "class1After",class1After
					if VERBOSE: print "class2After",class2After
					if correctClass1:
						for c1aIdx in range(len(class1After)):
							if class1After[c1aIdx] != c1aIdx: # c1aIdx is new index, class1After[c1aIdx] is old index
								for g in class1glyphs[ class1After[c1aIdx] ]:
									if g not in glyphs_removeOutlinesAndInstructions:
										subtable.ClassDef1.classDefs[g] = c1aIdx
					if correctClass2:
						for c2aIdx in range(len(class2After)):
							if class2After[c2aIdx] != c2aIdx: # c1aIdx is new index, class1After[c1aIdx] is old index
								for g in class2glyphs[ class2After[c1aIdx] ]:
									if g not in glyphs_removeOutlinesAndInstructions:
										subtable.ClassDef2.classDefs[g] = c2aIdx

def addCcmpLookup(ttx,ccmpSubs):
	if not ccmpSubs:
		return

	# create new ccmp subtable:
	subtable = MultipleSubst()
	subtable.LookupType = 2
	subtable.Format = 1
	subtable.Coverage = Coverage()
	subtable.Coverage.glyphs = [g[0] for g in ccmpSubs]
	sequence = []
	for g in ccmpSubs:
		s = Sequence()
		s.GlyphCount = len(g[1])
		s.Substitute = list(g[1])
		sequence += [s]
	subtable.Sequence = sequence

	# create new lookup as wrapper for subtable:
	lookup = Lookup()
	lookup.LookupType = 2
	lookup.LookupFlag = 0
	lookup.SubTable = [subtable]
	lookup.SubTableCount = 1
	
	# add lookup to lookup list:
	ttx["GSUB"].table.LookupList.Lookup += [lookup]
	ttx["GSUB"].table.LookupList.LookupCount = len(ttx["GSUB"].table.LookupList.Lookup)
	
	# add lookup list-index to ccmp features:
	newLookupIdx = len(ttx["GSUB"].table.LookupList.Lookup)-1
	# add new lookup (index) to ALL ccmp feature records (Q&D = quick & dirty):
	featureTags = []
	for r in ttx["GSUB"].table.FeatureList.FeatureRecord:
		if r.FeatureTag == "ccmp":
			r.Feature.LookupListIndex += [int(newLookupIdx)]
		featureTags += [r.FeatureTag]
	if "ccmp" not in featureTags:
		# determine location of feature record:
		featureTags += ["ccmp"]
		featureTags.sort()
		ccmpIdx = featureTags.index("ccmp")
		# create feature record:
		fr = FeatureRecord()
		fr.FeatureTag = "ccmp"
		fr.Feature    = Feature()
		fr.Feature.FeatureParams   = None
		fr.Feature.LookupCount     = 1
		fr.Feature.LookupListIndex = [int(newLookupIdx)]
		ttx["GSUB"].table.FeatureList.FeatureRecord[ccmpIdx:ccmpIdx] = [fr]
		# add feature to script/lang:
		for scriptRecord in ttx["GSUB"].table.ScriptList.ScriptRecord:
			# add feature's idx to scriptRecord.Script.DefaultLangSys:
			scriptRecord.Script.DefaultLangSys.FeatureCount += 1
			for fiIdx in range(len(scriptRecord.Script.DefaultLangSys.FeatureIndex)-1,-1,-1):
				if scriptRecord.Script.DefaultLangSys.FeatureIndex[fiIdx] >= ccmpIdx:
					scriptRecord.Script.DefaultLangSys.FeatureIndex[fiIdx] += 1 # we added a feature, so need to increase the reference-by-index of all that follow
			scriptRecord.Script.DefaultLangSys.FeatureIndex += [ccmpIdx]
			scriptRecord.Script.DefaultLangSys.FeatureIndex.sort() # are feature indices expected to be sorted in ascending order?
			if scriptRecord.Script.LangSysCount:
				for langSysRecord in scriptRecord.Script.LangSysRecord:
					# if langSysRecord.LangSysTag == "xxx": langSysRecord.LangSys = ...
					langSysRecord.LangSys.FeatureCount += 1
					for fiIdx in range(len(langSysRecord.LangSys.FeatureIndex)-1,-1,-1):
						if langSysRecord.LangSys.FeatureIndex[fiIdx] >= ccmpIdx:
							langSysRecord.LangSys.FeatureIndex[fiIdx] += 1 # we added a feature, so need to increase the reference-by-index of all that follow
					langSysRecord.LangSys.FeatureIndex += [ccmpIdx]
					langSysRecord.LangSys.FeatureIndex.sort() # are feature indices expected to be sorted in ascending order?

def removePostNames(ttx):
	ttx["post"].formatType = 3.0 # this automatically removes glyph name data

def addDummyDSIG(ttx):
	dsig = newTable("DSIG")
	dsig.data = "\x00\x00\x00\01\x00\x00\x00\x00"
	ttx["DSIG"] = dsig

def main(inPath, outPath): 
	if VERBOSE: print "Dieting %s..." % (os.path.basename(inPath))
	try:
		ttx = TTFont(inPath)
	except TTLibError:
		print "Cannot open %s" % inPath
		sys.exit(2)
	cmap = ttx["cmap"].getcmap(3,10)
	if not cmap: 
		cmap = ttx["cmap"].getcmap(3,1)
	if cmap: 
		umap = dict((u,n) for u, n in cmap.cmap.iteritems() )
#		nmap = dict((umap[k], k) for k in umap)
# glyph may be associated with more than one u!!!
		nmap = {}
		for k in umap:
			nmap.setdefault(umap[k],[]).append(k)
	else:
		if VERBOSE: print "'cmap' table misses a Windows-platform subtable."
		return

	def getDecompositionData(u,missingMarks):
	# inside so we can use umap, nmap ...
			udec = None
			try: 
				dec = unicodedata.decomposition(unichr(u))
				if len(dec) > 1:
					if not dec[:1] == "<":
						udec = [int(s, 16) for s in dec.split()]
						decall = 0
						for ud in udec:
							if ud in SKIP_MARKS_FINAL: # if mark is in SKIP_MARKS_FINAL we don't want to do any decomposition
								return 0
							if ud in umap:
								decall += 1
							else:
								if  ud not in SKIP_MARKS_FINAL \
								and ud     in MARK_GLYPH_CODEPOINT_RANGE:
									missingMarks += [unicodeIntToHexstr(ud)]
	#					if decall == len(udec) and decall == 1:
	#						print "SAME:",umap[u],[umap[ud] for ud in udec]
						if decall == len(udec) and decall > 1: # the last condition may go for the sake of allowing reference to same-shape glyphs
							return umap[u],[umap[ud] for ud in udec],udec[0] # last one is the one to check next
			except ValueError: 
				return 0
			return 0

	markGlyphs = getMarkGlyphs(ttx)
	
	if not testFont(ttx,umap,nmap,markGlyphs):
		if VERBOSE: print "This font is useless. Ignoring it."
		return

	glyphOrder = ttx.getGlyphOrder()

	glyphs_removeOutlinesAndInstructions = []
	ccmpSubsDict = {}
	linesDict = {}
	missingMarks = []
	if umap:
		for u in umap:
			decomp = getDecompositionData(u,missingMarks)
			decompLast = deepcopy(decomp)
			while decomp:
				decomp = getDecompositionData(decomp[2],missingMarks) # check if the base char is a composed one too!
				# cf: 01E0;LATIN CAPITAL LETTER A WITH DOT ABOVE AND MACRON;Lu;0;L;0226 0304;;;;N;LATIN CAPITAL LETTER A DOT MACRON;;;01E1;
				if decomp:
					decompLast[1][0:1] = deepcopy(decomp[1])
			if decompLast:
				ccmpSubsDict[decompLast[0]] = decompLast[1]
				linesDict[   decompLast[0]] = "  sub %s by %s;" % (decompLast[0], " ".join(decompLast[1]))
				glyphs_removeOutlinesAndInstructions += [decompLast[0]]
	# sort by glyph order!
	ccmpSubs = []
	lines    = []
	for g in glyphOrder:
		try:    ccmpSubs += [(g,ccmpSubsDict[g])]
		except: pass
		try:    lines    += [ linesDict[g] ]
		except: pass
	if len(ccmpSubsDict) != len(ccmpSubs):
		if VERBOSE: print "(Lost substitutions when creating ccmpSubs.)"
	if len(linesDict) != len(lines):
		if VERBOSE: print "(Lost substitutions when creating lines.)"

	# report missing marks:
	missingMarks = cleanUpList(missingMarks)
	missingMarks.sort()
	if missingMarks:
		if VERBOSE: print "For more effective decomposition you might add the following marks:"
		if VERBOSE: print " ".join(missingMarks)
	
	# output AFDKO syntax .fea file:
	if len(lines):
		ccmpfea  = [ "lookup ccmpUnicodeDecomp {" ]
		ccmpfea += lines
		ccmpfea += [ "} ccmpUnicodeDecomp;"       ]
		if SAVE_FEA_FILE:
			saveFile("\n".join(ccmpfea),os.path.splitext(outPath)[0]+".ccmp.fea")
	else:
		if VERBOSE: print "Nothing there to decompose."

	if REMOVE_PRECOMPOSED_OUTLINES       and lines: # only makes sense if there's something to decompose
		removeOutlines(ttx,glyphs_removeOutlinesAndInstructions)
	if REMOVE_PRECOMPOSED_FROM_GPOS_KERN and lines: # only makes sense if there's something to decompose
		removeGPOSkern(ttx,glyphs_removeOutlinesAndInstructions)
	if REMOVE_ALL_BUT_WIN_CMAP_SUBTABLES:
		removeAllButWinCmapSubtable(ttx)
	if REMOVE_ALL_BUT_WIN_NAME_RECORDS \
	or RENAME_FONT: # enforce removing non-Win records when renaming the font!
		removeAllButWinNameRecords( ttx)
	if RENAME_FONT:
		renameFont(                 ttx)
	if ADD_DUMMY_DSIG:
		addDummyDSIG(               ttx)
	if DECOMPOSE_PRECOMPOSED_IN_CCMP     and lines:# only makes sense if there's something to decompose
		addCcmpLookup(              ttx,ccmpSubs)
	if REMOVE_POST_GLYPHNAMES:
		removePostNames(            ttx)

	tempPath = outPath+"temp"
	if VERBOSE: print "Saving %s..." % (outPath)
	ttx.save( outPath )
	ttx.close()
	ttx = None
	inSize = os.path.getsize(inPath)
	outSize = os.path.getsize(outPath)
	if VERBOSE: print "Diet efficiency: %s%% (from %s to %s bytes)" % (float(int((1 - float(outSize)/inSize) * 10000))/100, inSize, outSize)

	# validate:
	if OTS_SANITISE: 
		error = 0
		try:
			p = Popen([r"%s" % OTS_PATH_OR_COMMAND, r"%s" % outPath, r"%s" % tempPath ],stderr=PIPE)
		except:
			p = 0
			if VERBOSE and OTS_SANITISE: print "ot-sanitise not found. Install https://github.com/khaledhosny/ots"
		if p:
			stdoutdata, stderrdata = p.communicate()
			if stderrdata: # if no problems are found, ot-sanitise doesn't output anything
				error = 1
				if OTS_SANITISE:
					print "ot-sanitise did not validate the simplified font. ", 
					if OTS_SANITISE > 1: print "Deleting it."
				else:
					if VERBOSE: print "ot-sanitise validated this font."
				for line in stderrdata.strip().replace("\r\n","\n").replace("\r","\n").split("\n"):
					if VERBOSE: print "    %s" % line.strip()
		p=None; stderrdata=None; stdoutdata=None
		if error:
			# delete ot-sanitise file
			# and the font file since it is invalid anyway:
			if os.path.exists( tempPath ):
				os.remove( tempPath )
			if os.path.exists( outPath  ) and OTS_SANITISE > 1:
				os.remove( outPath  )
		else:
			# always delete ot-sanitise file:
			if os.path.exists( tempPath ):
				os.remove( tempPath )
	outPath=None; tempPath=None

if __name__ == "__main__":
	args = sys.argv
	if len(args) < 2: 
		args.append("-h")
	inPath, outPath = handleOptions()
	main(inPath, outPath)
	if VERBOSE: print "Done."
