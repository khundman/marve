#!/usr/bin/env python
# encoding: utf-8
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

class Stats:
    """ Holds statistics on measurement extraction processing
    
    Attributes:
        total_sentences (int): Total number of sentences processed for a given chunk of text
        total_measurements (int): Total measurements found for a given chunk of text
    """
    def __init__(self):
        self.total_sentences = 0
        self.total_measurements = 0       

    def print_summary(self):
        # All results (make function)
        print ("Total Sentences Parsed: " + str(self.total_sentences))
        print ("Total Measurements Parsed: " + str(self.total_measurements))
        # print ("Total Measurement Types Found: " )
        # for key, value in stats.pattern_cnts["type"].iteritems():
        #     print "   " + key + ": " + str(value)


class Annotations:
    """ Tokens and depedency objects from CoreNLP and various lookups for readability and processing
    
    Attributes:
        tokens (list): Token objects from CoreNLP
        deps (list): Word dependency objects from CoreNLP
        matches (list): Parsed measurement objects
        lookup (dict of str: dict of str: str): look up various token characteristics by token index
        tok_start (dict of str: str): look up token index by beginning character index
        tok_end (dict of str: str): look up token index by ending character index
        index_lookup (dict of str: str): look up token index by word
        
    """
    def __init__(self, tokens, dependencies):
        self.tokens = tokens
        self.deps = dependencies
        self.matches = [] # holds format types, indices, and words for measurement numbers and units found in a sentence  

        # Handy lookups
        self.lookup = {}
        self.tok_start = {}
        self.tok_end = {}
        self.index_lookup = {}
        self.lookup[0] = {"pos" : "", "word": ""} #0 not included in tokens, but included in dependencies
        
        for f in self.tokens:
            self.tok_start[f["characterOffsetBegin"] - self.tokens[0]["characterOffsetBegin"]] = f["index"]
            
            self.tok_end[f["characterOffsetEnd"] - self.tokens[0]["characterOffsetBegin"]] = f["index"]

            self.lookup[f["index"]] = {}
            self.lookup[f["index"]]["word"] = f["originalText"]
            self.lookup[f["index"]]["lemma"] = f["lemma"]
            self.lookup[f["index"]]["pos"] = f["pos"]
            self.lookup[f["index"]]["start"] = f["characterOffsetBegin"]
            self.lookup[f["index"]]["end"] = f["characterOffsetEnd"]
            self.lookup[f["index"]]["ner"] = f["ner"]
            self.lookup[f["index"]]["after"] = f["after"]

            self.index_lookup[f["word"]] = f["index"]


    def augment_match(self, grobid):
        """ 
        Add measurement info to list for further processing.
        """

        key = None
        if grobid["type"] == "value":
            key = "quantity"
        elif grobid["type"] == "interval" and "quantityLeast" in grobid:
            key = "quantityLeast"
        elif grobid["type"] == "interval" and not "quantityLeast" in grobid:
            key = "quantityMost"
        else:
            raise ValueError("Need to handle another type of Grobid key in addition to (quantity, qunatity least, quantity most")

        format, unit, unit_idx, num, num_idx = "", "", "", "", ""
        
        if "rawUnit" in grobid[key]:
            #The format of the measurement determines the traversal of the dependency pattern JSON
            if grobid[key]["tokenIndex"] in grobid[key]["rawUnit"]["tokenIndices"]:
                format = "attached"
            elif grobid[key]["rawUnit"]["after"] == "-":
                format = "hyphenated"
            else:
                format = "space_between"

            unit = grobid[key]["rawUnit"]["name"]
            unit_idx = grobid[key]["rawUnit"]["tokenIndices"]

        # In cases where unit is missing but "quantified" is present, key off of "quantified" for related words
        elif "quantified" in grobid:
            format = "space_between"
            unit = grobid["quantified"]["normalizedName"]

            # see hyphen issue mentioned in grobid.py
            if "tokenIndex" in grobid["quantified"]:
                unit_idx = [grobid["quantified"]["tokenIndex"]]
            else:
                return

        if key == "quantity": num = grobid[key]["rawValue"] 
        if key == "quantityMost" and "quantityLeast" in grobid: num = grobid["quantityLeast"]["rawValue"] + " to " +  grobid[key]["rawValue"]

        self.matches.append({
            "measurement_format" : format, 
            "unit_idx" : unit_idx, 
            "unit" : unit, 
            "num_idx" : str(grobid[key]["tokenIndex"]), 
            "num" : num,
            "grobid" : grobid
        })
    

    def check_output(self, sentence, stats):
        """ 
        Check to see if coreNLP was able to successfully create a parse tree. 
        If the words (dependentGloss/governorGloss) are missing from the dependency objects, the parse was unsuccessful
        """    
        for dep in self.deps:
            if not "dependentGloss" in dep or not "governorGloss" in dep:
                stats.parse_error(sentence)
                return False
        return True

