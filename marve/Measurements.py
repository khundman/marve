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


import networkx as nx
import os
import codecs
from pycorenlp import StanfordCoreNLP
import matplotlib.pyplot as plt
import re
import operator
import json
from collections import OrderedDict
import logging
# custom
from classes import Stats, Annotations
from grobid import grobid_quantities


##################################################################################
# Globals
##################################################################################
basedir = os.path.abspath(os.path.dirname(__file__))
stats = Stats()
A = None # global annotations object
Num = None # global sentence object
G = None # global dependency tree object

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S',
                    filename=os.path.join(basedir, 'measurement.log'))
##################################################################################


def _build_graph(show=False):
    """Load word dependencies into graph using networkx. Enables easy traversal of dependencies for parsing particular patterns.
    One graph is created for each sentence.

    Args:
        show (bool): If set to True, labeled visualization of network will be opened via matplotlib for each sentence

    Returns:
        None: Global variable G is set from within function

    """
    global G
    G = nx.Graph()
    node_labels, edge_labels = {}, {}
    for idx, dep in enumerate(A.deps):

        types = ["dependent", "governor"]

        # nodes, labels
        for x in types:
            G.add_node(str(dep[x]), word=dep[x + "Gloss"], pos=A.lookup[dep[x]]["pos"])
            node_labels[str(dep[x])] = dep[x + "Gloss"] + " : " + A.lookup[dep[x]]["pos"]
        
        # edges, labels
        G.add_edge(str(dep[types[0]]), str(dep[types[1]]), dep=dep["dep"])
        edge_labels[(str(dep[types[0]]), str(dep[types[1]]))] = dep["dep"]
       
    if show == True:
        pos = nx.spring_layout(G)
        nx.draw_networkx(G,pos=pos, labels=node_labels, node_color="white", alpha=.5)
        nx.draw_networkx_edge_labels(G,pos=pos,edge_labels=edge_labels)
        plt.show()



#########################################
# Dependency / POS parsing functions
#########################################

def _get_connected(edge, idx):
    """If an edge connects to a node (word), return the index of the node

    Args:
        edge (tuple): Contains token indices of two connect words and the dependency type between them - e.g. ('11', '14', {'dep': 'nmod:at'})
        idx (int): Token index of word 

    Returns:
        str or None: str if connected word is found in provided edge, None if not 
    """
    if str(edge[0]) == str(idx) and A.lookup[int(edge[1])]["word"] != Num:
        return edge[1] 
    elif str(edge[1]) == str(idx) and A.lookup[int(edge[0])]["word"] != Num:
        return edge[0]



def _get_cousin(sibling_idx, dep_type_list, visited_nodes={}):
    """Find a second degree relation within the dependency graph. 
    Used to find subject in a sentence when the measurement unit is a direct object, for example. 

    Args:
        sibling_idx (str): Token index of the sibling node through which to find the cousin
        dep_type_list (list): Allowable dependency types connecting sibling to cousin

    Returns:
        list: cousin words meeting POS and dependency criteria
    """
    words = [] #Visited nodes prevent recursion from bouncing between two "VB" nodes


    for dep_type in dep_type_list:
        for edge in G.edges(data=True):
            
            cousin_idx = _get_connected(edge, sibling_idx)

            allowed_pos = ["NN", "PR"]
            if cousin_idx and dep_type in edge[2]['dep'] and any(x in A.lookup[int(cousin_idx)]['pos'] for x in allowed_pos):
                words.append(G.node[cousin_idx]['word'])

            # Go to second cousin if cousin is a verb
            elif cousin_idx and dep_type in edge[2]['dep'] and "VB" in A.lookup[int(cousin_idx)]['pos'] and (not cousin_idx in visited_nodes or visited_nodes[cousin_idx] < 2):
                words.extend(_get_cousin(cousin_idx, ["nsubj", "nsubjpass", "acl"], visited_nodes=visited_nodes))

            if cousin_idx: 
                if cousin_idx in visited_nodes:
                    visited_nodes[cousin_idx] += 1
                else:
                    visited_nodes[cousin_idx] = 1
    return set(words)



def _add_related(related, dep, all_related, index, connector=None):
    """Adds a word (and its metadata) related to a measurement to the list of all related words for that measurement 

    Args:
        related (str): related token/word
        dep (str): the dependency type connecting the unit to the related word
        all_related (list): existing list of "related" objects to be augmented
        index (str): token index of related word
        connector (str): if related word is cousin of unit (not sibling) then connecter is word between

    Returns:
        list: all related words for a given measurement (augmented with new 'related' passed in)
    """
    doc = {}
    doc["relationForm"] = dep
    doc["rawName"] = related
    doc["tokenIndex"] = int(index)
    doc["offsetStart"] = A.lookup[int(index)]["start"]
    doc["offsetEnd"] = A.lookup[int(index)]["end"]
    doc["connector"] = "" if connector == None else connector
    if not doc in all_related:
        all_related.append(doc)
    return all_related



def _add_descriptors(related):
    """For related words found for a measurement (usually nouns), add any connected adjectives, compounds, or modifiers.

    Args:
        related (list): objects containing related words and their metadata

    Returns:
        list: original list of related objects augmented with additional descriptor words
    """

    for r in related:
        r["descriptors"] = []
        for edge in G.edges(data=True):
            sibling_idx = _get_connected(edge, r["tokenIndex"])
            if sibling_idx and (A.lookup[int(sibling_idx)]["pos"] == "JJ" or edge[2]["dep"] in ["amod", "compound"]):
                r["descriptors"].append(
                    {
                        "tokenIndex": sibling_idx,
                        "rawName": A.lookup[int(sibling_idx)]["word"]
                     }
                )

            if sibling_idx and "NN" in A.lookup[int(sibling_idx)]["pos"] and "amod" in edge[2]["dep"]:
                additional_related = _get_cousin(sibling_idx, ["nmod"])
                for add in set(additional_related):
                    related = _add_related(add, "nmod", related, A.index_lookup[add], connector=G.node[sibling_idx]['word'])
    return related


def _check_criteria(dep, dep_obj, all_related, edge, sibling_idx):
    """ If measurement is found, runs processed sentence through valid dependency patterns 
        (from JSON file) to find additional words related to measurements

    Args:
        dep (str): dependency type present in dependency patterns JSON
        dep_obj (dict): object containing accepted POS types and measurement formats for a given dependency type
        all_related (list): contains words related to a measurement to be augmented if valid pattern is found
        edge (list): Connected node (word) indices and dependency type between
        sibling_idx (str): token index of word connected to unit

    Returns:
        list: related words and metadata
    """
    # Check for a matching dependency type
    related = []
    
    if edge[2]["dep"] == dep:
        # Check for matching POS type(s)
        for pos_logic in dep_obj.keys():
            connector = None

            if isinstance(dep_obj[pos_logic], dict):
                for pos in dep_obj[pos_logic].keys(): 

                    # Check for allowed part of speech tags in matched dependency patterns
                    if (pos_logic == "pos_in" and pos in G.node[sibling_idx]["pos"]) or (pos_logic == "pos_equals" and pos == G.node[sibling_idx]["pos"]):
                        pass
                    elif pos_logic == "pos_not":
                        if not [False if not_pos == G.node[sibling_idx]["pos"] else True for not_pos in dep_obj.keys()]: continue
                    else:
                        continue
                    
                    # if no additional checks, have a match
                    if dep_obj[pos_logic][pos] == None or any(y in dep_obj[pos_logic][pos] for y in [None, "add_sibling"]):
                        all_related = _add_related(G.node[sibling_idx]['word'], dep, all_related, A.index_lookup[G.node[sibling_idx]['word']])

                    # if additional checks are required, process further
                    if dep_obj[pos_logic][pos]:
                        if "get_cousin" in dep_obj[pos_logic][pos]:      
                            related.extend(_get_cousin(sibling_idx, dep_obj[pos_logic][pos]["get_cousin"]))
                            connector = G.node[sibling_idx]['word']

                        if "special" in dep_obj[pos_logic][pos]:
                            if dep == "compound" and pos == "NN":    
                                related = [G.node[sibling_idx]['word']]

                        if None in related:
                            related.remove(None)
                        
                        # Allows for getting cousin and returning sibling
                        if "else" in dep_obj[pos_logic][pos].keys() and dep_obj[pos_logic][pos]["else"] == "always":
                            all_related = _add_related(G.node[sibling_idx]['word'], dep, all_related, A.index_lookup[G.node[sibling_idx]['word']], connector=connector)
                        if len(related) > 0 and isinstance(related, list):
                            for x in related:
                                if x != None:
                                    all_related = _add_related(x, dep, all_related, A.index_lookup[x], connector=connector)
                        elif "else" in dep_obj[pos_logic][pos].keys() and dep_obj[pos_logic][pos]["else"] == True:
                            all_related = _add_related(G.node[sibling_idx]['word'], dep, all_related, A.index_lookup[G.node[sibling_idx]['word']], connector=connector)

    return all_related




def _parse_patterns(unit_idx, measurement_format, patterns_file):
    """ Loads depedency patters JSON file and uses "_check_criteria" to look for words related to measurement (connected via unit token)

    Args:
        unit_idx (list): index or indices of measurement unit token(s)
        measurement_format (str): indicates form of measurement value + unit (attached: 10m, space between: 10 m, hyphenated: 10-m)

    Returns:
        list: related words and metadata
    """              

    all_related = []

    for edge in G.edges(data=True):
        for idx in unit_idx:
            sibling_idx = _get_connected(edge, idx)
            if sibling_idx:
                with open(os.path.join(basedir, patterns_file), "r") as tree:
                    tree = json.load(tree)

                    for dep in tree["dep"].keys():
                        if tree["dep"][dep]["enhanced"] == True:
                            for inner_dep in tree["dep"][dep].keys():
                                if isinstance(tree["dep"][dep][inner_dep], dict) and measurement_format in tree["dep"][dep][inner_dep]["measurement_types"]:
                                    full_dep = dep + ":" + inner_dep
                                    full_dep_obj = tree["dep"][dep][inner_dep]
                                    all_related = _check_criteria(full_dep, full_dep_obj, all_related, edge, sibling_idx)

                        elif measurement_format in tree["dep"][dep]["measurement_types"]:
                            all_related = _check_criteria(dep, tree["dep"][dep], all_related, edge, sibling_idx)

                    for x in range(0, len(tree["word"]["or"])):
                        if G.node[sibling_idx]["word"] == tree["word"]["or"][x]:
                             related = _get_cousin(sibling_idx, ["nsubj"])
                             for r in related:
                                all_related = _add_related(r, "operator", all_related, A.index_lookup[r])

    all_related = _add_descriptors(all_related)

    return all_related



def _get_related(stats, match, patterns_file):
    """ Calls _parse_patterns() to get words related to a measurement and provides de-duplication between related words and grobid response

    Args:
        stats (Stats object): Global object used to track parsing behaviors
        match (dict): information on measurements and units extracted by Grobid

    Returns:
        list: related words and metadata
    """        
    all_related = None
    measurement_formats = ["space_between", "attached", "hyphenated"]

    all_related = _parse_patterns(match["unit_idx"], match["measurement_format"], patterns_file)
    if all_related == None:
        all_related = _parse_patterns(match["unit_idx"], ["uncertain"], patterns_file)

    # get words like approximately
    adverbs = _parse_patterns([match["num_idx"]], match["measurement_format"], patterns_file)
    for_removal = [] 
    for a in adverbs:
        if a["relationForm"] != "advmod":
            for_removal.append(a)
        else:
            [a.pop(key, None) for key in ["descriptors", "connector"]] #not relevant for adverbs
    [adverbs.remove(a) for a in for_removal]

    if adverbs:
        match["grobid"]["adverbs"] = adverbs

    # Check to make sure related isn't already a number, unit, or quantified thing identified by Grobid 
    potential_keys = ["quantity", "quantityLeast", "quantityMost", "quantified"]

    if all_related:
        for key in potential_keys:
            for related in all_related:
                if key in match["grobid"]:
                    num, unit, quantified = "", "", ""
                    if "rawValue" in match["grobid"][key]: num = match["grobid"][key]["rawValue"]
                    if "rawUnit" in match["grobid"][key]: unit = match["grobid"][key]["rawUnit"]["name"]
                    if "normalizedName" in match["grobid"][key]: quantified = match["grobid"][key]["normalizedName"]
                    
                    if related["rawName"] in [num, unit, quantified] or related["rawName"] == num + unit or (quantified in related["rawName"] and not quantified == ""):
                        all_related.remove(related)

                        if related["rawName"] == unit:
                            for k in related.keys():
                                if not k in match["grobid"][key]["rawUnit"]:
                                    match["grobid"][key]["rawUnit"][k] = related[k]
 
                        elif related["rawName"] == quantified:
                            for k in related.keys():
                                if not k in match["grobid"][key]:
                                    match["grobid"][key][k] = related[k]
    return all_related


def _simplify_results(match):
    """WORK IN PROGRESS: Prune metadata from extracted measurements and related words for more readable output

    Args:
        match (dict): Object contatining all metadata about extraction types, locations, relationships within sentence

    Returns:
        list: contains 4 items, extracted numeric value or range (list), unit(s) (list), qunatified words identified by Grobid (str), related words (str)
    """

    keys = []
    simplified = {}
    simplified["value"] = []
    
    if match["type"] == "value":
        keys = ["quantity"]
    elif match["type"] == "interval":
        keys = ["quantityLeast", "quantityMost"]

    for key in keys:
        if key in match:
            if "parsedValue" in match[key]:
                simplified["value"].append(match[key]["parsedValue"])
            elif "rawValue" in match[key]:
                simplified["value"].append(match[key]["rawValue"])
            else:
                return None

            simplified["unit"] = match[key]["rawUnit"]["name"] if "rawUnit" in match[key] else ""

    if len(simplified["value"]) == 1:
        simplified["value"] = simplified["value"][0]

    simplified["quantified"] = {}
    simplified["related"] = {}

    if "quantified" in match: 

        if simplified["unit"] == "":
            simplified["unit"] = match["quantified"]["normalizedName"]
        
        simplified["quantified"][match["quantified"]["normalizedName"]] = []
        if "descriptors" in match["quantified"]:

            match["quantified"]["descriptors"].sort(key=lambda x: int(x["tokenIndex"]), reverse=False)

            for x in match["quantified"]["descriptors"]:
                simplified["quantified"][match["quantified"]["normalizedName"]].append(x["rawName"])

    if match["related"]:
        for r in match["related"]:
            simplified["related"][r["rawName"]] = []

            if "descriptors" in r:
                r["descriptors"].sort(key=lambda x: int(x["tokenIndex"]), reverse=False)
                
                for z in r["descriptors"]:
                    simplified["related"][r["rawName"]].append(z["rawName"])

    
    return simplified



def _reconstruct_sent(parsed_sentence):
    """Reconstruct sentence from CoreNLP tokens - raw sentence text isn't retained by CoreNLP after sentence splitting and processing

    Args:
        parsed_sentence (dict): Object containing CoreNLP output

    Returns:
        str: original sentence
    """
    sent = ""
    for x in range(0, len(parsed_sentence["tokens"])):
        sent += parsed_sentence["tokens"][x]['originalText']
        if x+1 != len(parsed_sentence["tokens"]):
            # Use character indices from tokens to ensure correct spacing when reconstructing 
            num_spaces = parsed_sentence["tokens"][x+1]["characterOffsetBegin"] - parsed_sentence["tokens"][x]["characterOffsetEnd"]
            for y in range(0, num_spaces):
                sent += " "
    return sent


#########################################
# Top-Level function
#########################################
def extract(content, corenlp_endpoint, grobid_endpoint, dependency_patterns_file, output_file=None, show_graph=False, pretty=False, simplify=False):
    """ Top-level user interface to parsing measurements and related words

    Args:
        content (str): sentence or paragraph to be parsed (shouldn't be much larger)
        corenlp_endpoint (str): host + port of CoreNLP service (e.g. "http://localhost:9000")
        grobid_endpoint (str): host + port of grobid service (e.g. "http://localhost:8080")
        dependency_patterns (str): filepath to dependency patterns JSON file
        output_file (optional: str): file to write output to
        show_graph (bool): Will show network visualization of sentence dependencies if True
        pretty (bool): JSON output will be pretty printed if True, else one JSON doc per line (JSONL)
        simplify (bool): If True provides bare bones output with only extractions and not metadata about indices, types, etc.

    Returns:
        List of objects: containing parsed measurement info
        (optionally write to file)
    """  

    all_extractions = []

    out = None
    if output_file:
        out = codecs.open(output_file, "a", encoding="utf-8")

    if len(content) < 5: return None

    nlp = StanfordCoreNLP(corenlp_endpoint)
    output = nlp.annotate(content, properties={'outputFormat':'json', 'timeout':'9999'})
    if isinstance(output, basestring):
        output = json.loads(output.encode("latin-1"), strict=False)

    if "sentences" in output and isinstance(output["sentences"],list):
        for i in range(0, len(output["sentences"])):
            s_str = _reconstruct_sent(output["sentences"][i])
        
            #Enhanced dependencies have different key names in JSON depending on version of CoreNLP
            dep_key = "enhanced-plus-plus-dependencies" if not "collapsed-ccprocessed-dependencies" in output["sentences"][i] else "collapsed-ccprocessed-dependencies"
            
            global A 
            A = Annotations(output["sentences"][i]["tokens"], output["sentences"][i][dep_key])

            if A.check_output(output["sentences"][i], stats) == True:
                
                stats.total_sentences += 1
                G = _build_graph(show=show_graph)
                grobid_response = grobid_quantities(s_str, A, grobid_endpoint)

                if isinstance(grobid_response, dict) and "measurements" in grobid_response:
                    for quantity in grobid_response["measurements"]:
                        A.augment_match(quantity)

                    stats.total_measurements += len(A.matches)

                    for idx, match in enumerate(A.matches):
                        
                        global Num
                        Num = match["num"]

                        match["sentence"] = i+1
                        match["grobid"]["related"] = _get_related(stats, match, dependency_patterns_file)

                        # Remove fields used for processing but not to be shown to user
                        remove = ["adverbs", "num", "unit", "connector", "form", "sentence", "num_idx", "unit_idx", "measurement_format"]
                        [match.pop(x, None) for x in remove]
                        sort_order = ['adverbs', 'type', 'quantity', 'quantityLeast', 'quantityMost', 'quantified', 'related']
                        match_ordered = OrderedDict(sorted(match["grobid"].iteritems(), key=lambda (k, v): sort_order.index(k)))

                        if simplify:
                            simplified_sort_order = ['value', 'unit', 'quantified','related']
                            simplified = _simplify_results(match_ordered)

                            if simplified:
                                match_ordered = OrderedDict(sorted(simplified.iteritems(), key=lambda (k, v): simplified_sort_order.index(k)))

                        if pretty and not simplify:
                            if out: out.write(json.dumps(match_ordered, ensure_ascii=False, indent=4))
                            if idx != len(A.matches) - 1 and out: out.write(",\n")
                        
                        elif out:
                            out.write(json.dumps(match_ordered, ensure_ascii=False) + "\n")

                    all_extractions.extend(A.matches)

            else:
                logging.warning("CoreNLP parsing failed for sentence: %s" %(s_str))                
    else:
        logging.warning("CoreNLP parsing failed for content: %s" %(content))

    if out: out.close()

    logging.info("Total sentences parsed: %s" %(str(stats.total_sentences)))
    logging.info("Total measurements found: %s" %(str(stats.total_measurements)))
    stats.print_summary()

    return all_extractions

