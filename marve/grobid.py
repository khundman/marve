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

import re
import subprocess
import logging
import json

def grobid_quantities(sentence, a, endpoint):
    """
    a = annotations
    """
    """Pass sentence text to Grobid server on port 8080 for measurement parsing

    Args:
        sentence (str): Sentence to be parsed
        a (Annotations object): object containing relevant CoreNLP output

    Returns:
        dict: object containing Grobid output
    """

    # $ needs to be escaped when passed via subprocess
    sentence = re.sub("\$", "\\$", sentence)
    sentence = re.sub("\"", '\\"', sentence)
    sentence = re.sub("%", '%25', sentence)
    sentence = re.sub("`","'", sentence)
    sentence = re.sub("'",'\\"', sentence)

    if endpoint[len(endpoint)-1:] == "/":
        endpoint = endpoint[:len(endpoint)-1]

    response = None
    try:
        response = subprocess.check_output('curl -X POST -d text="' + sentence + '" ' + endpoint + '/processQuantityText', shell=True)
    except:
        logging.error("Invalid subprocess call for: %s" %(sentence))
    quantities = {}
    try:
        quantities = json.loads(response)
    except ValueError as e:
        print ('No Grobid response for: %s' %(sentence))
        logging.warning('No Grobid response for: %s' %(sentence))
        return ""

    #Add token index for num, unit, quantified if available
    if isinstance(quantities, dict):
        for q in quantities["measurements"]:

            key = ""
            if q["type"] == "value":
                key = "quantity"
            # if Grobid doesn't parse interval correctly, sometimes only 'QuantityLeast' or 'QuantityMost' is available
            if q["type"] == "interval":
                if "quantityLeast" in q:
                    key = "quantityLeast"
                elif "QuantityMost" in q:
                    key = "quantityMost"
                else:
                    return {}

            if q["type"] == "listc":
                return {}

            if key == "":
                logging.error('Unknown Grobid key resulting from parse of: %s' %(sentence))
                print "Unknown Grobid key resulting from parse of: %s" %(sentence)

            # Grobid doesn't pick up negatives
            if sentence[sentence.find(q[key]["rawValue"]) - 1] == "-":
                q[key]["parsedValue"] = float("-" + str(q[key]["parsedValue"]))
                q[key]["rawValue"] = "-" + str(q[key]["rawValue"])
                q[key]["offsetStart"] -= 1

            if q[key]["offsetStart"] in a.tok_start:
                q[key]["tokenIndex"] = a.tok_start[q[key]["offsetStart"]]
            else:
                print "Not finding token index for Grobid Quantity value in CoreNLP output. Sentence: %s" %(sentence)
                logging.error("Not finding token index for Grobid Quantity value in CoreNLP output. Sentence: %s" %(sentence))
                return {}

            if "rawUnit" in q[key]:
                q[key]["rawUnit"]["after"] = a.lookup[q[key]["tokenIndex"]]["after"]
                q[key]["rawUnit"]["tokenIndices"] = []

                if q[key]["rawUnit"]["offsetStart"] in a.tok_start: 
                    q[key]["rawUnit"]["tokenIndices"].append(str(a.tok_start[q[key]["rawUnit"]["offsetStart"]])) 
                if q[key]["rawUnit"]["offsetEnd"] in a.tok_end: 
                    q[key]["rawUnit"]["tokenIndices"].append(str(a.tok_end[q[key]["rawUnit"]["offsetEnd"]]))
                
                if q[key]["rawUnit"]["offsetStart"] == q[key]["offsetEnd"]: 
                    q[key]["rawUnit"]["tokenIndices"].append(str(q[key]["tokenIndex"])) 
                q[key]["rawUnit"]["tokenIndices"] = list(set(q[key]["rawUnit"]["tokenIndices"]))

            if "quantified" in q:
                
                # often times Grobid with return a phrase where normalized name is in middle. In this case, "offsetStart" identifies the wrong token 
                add_to_offset = 0
                normalized_idx, words = None, None
                if " " in q["quantified"]["rawName"]:
                    words = q["quantified"]["rawName"].split(" ")
                    for i,w in enumerate(words):
                        if not q["quantified"]["normalizedName"] in w:
                            add_to_offset += (len(w) + 1) # +1 for space that was split on
                        else:
                            break

                q["quantified"]["offsetStart"] += add_to_offset

                if q["quantified"]["offsetStart"] in a.tok_start:
                    q["quantified"]["tokenIndex"] = a.tok_start[q["quantified"]["offsetStart"]]
                else:
                    logging.warning("Not finding token index for Grobid quantified word in CoreNLP output. Sentence: %s" %(sentence))
                     #hyphen causing issue - Grobid doesn't treat hyphenated clause as one word 
                        # example error sentence: "Macroscopic examination of the CNS revealed micrencephaly with a whole-brain weight of 84 grams."
                       
    return quantities
