# Marve
A measurement relation extractor

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Marve leverages [grobid-quantities](https://github.com/kermitt2/grobid-quantities) and [Stanford CoreNLP](http://stanfordnlp.github.io/CoreNLP) to extract and normalize measurements and their related entities and descriptors from natural language text. 

```shell
	
	sample = "The patient returned to Europe at 28 weeks of gestation."

	#Simplified output
	#-----------------
	value: "28"
	unit: "weeks"
	quantified: "gestation"
	related: ["patient", "Europe"]
```

Marve employs grobid-quantities to find measurement values, units, and a limited set of "quantified" substances using linear CRF models trained on a labeled corpus of text. CoreNLP is then used to link measurements to related words in the sentence using word dependencies and POS tags from CoreNLP. Common dependency/POS patterns relating measurements to other words/entities are specified in `/marve/dependency_patterns.json` and can be adjusted without modifying code. 

## Installation

Running Marve requires grobid-quantities and CoreNLP to be running:

Download and unzip [CoreNLP](http://stanfordnlp.github.io/CoreNLP/download.html):
```shell
curl -LOk "http://nlp.stanford.edu/software/stanford-corenlp-full-2016-10-31.zip" | unzip <path to CoreNLP>/stanford-corenlp-full-2016-10-31.zip
```

Run (requires Java 8):
```shell
cd <path to CoreNLP>/stanford-corenlp-full-2016-10-31 | java -mx4g -cp "*" edu.stanford.nlp.pipeline.StanfordCoreNLPServer 9000
```

Install grobid by following instructions [here](http://grobid.readthedocs.io/en/latest/Install-Grobid/) </br></br>
Then follow [grobid-quantities instructions](https://github.com/kermitt2/grobid-quantities) to install, build, train, and run

Install Marve:</br>
`pip install marve`

## Usage
Once both CoreNLP and grobid-quantities are running, Marve can be used as such:

```shell
# coding: utf-8

from marve import Measurements as m

# Strings longer than a paragraph should be split before passing to Marve
_test = "The patient returned to Europe at 28 weeks of gestation."

coreNLP = "http://localhost:9000"
grobid = "http://localhost:8080"
patterns = "dependency_patterns.json"
write_to = "sample_output.txt"

m.extract(_test, coreNLP, grobid, patterns, write_to, show_graph=False, pretty=True, simplify=False)
````

(This example can be found in `sample.py`)

<b>IMPORTANT</b>: Text should be in sentence or paragraph chunks before passing to Marve.

<b> Note </b>: The first time Marve is run, a timeout error might be thrown due to longer CoreNLP model loading times. If this happens, run again and CorenLP should run properly.

## Dependency and Part-of-Speech Patterns
Marve will only return words related to measurements if they meet criteria laid out in the dependency pattern file `/marve/dependency_patterns.json`.

Take the phrase `"a spatial resolution of 10m"`. Marve uses a graph to represent each sentence, where edges are the dependencies between words (represented in green ovals below) and nodes are words and their part-of-speech (POS) labels (represented in blue). 

![example](https://github.jpl.nasa.gov/hundman/marve/blob/master/blob/example.png)

There are a handful of general patterns that relate measurement units, values, and other related words or entities in a sentence. For instance, units are generally connected to values via the numerical modifier (`"nummod"`) dependency (see above). Nominal modifiers (`"nmod"`) is then a common dependency linking units to the thing being quantified. Common patterns linking values, units, and related words have been defined in `/marve/dependency_patterns.json`, and the bit of JSON that would match `"m"` to `"resolution"` in our above example is:


```shell
"nmod": {
    "enhanced": true,
    "of":{
        "measurement_types": ["space_between", "attached"],
        "pos_in":{
            "NN": null
        }
    }
}
```

Here's how this example matches:</br></br>
1. `nmod` is the dependency type between `m` and `resolution`</br></br>
2. Since we utilized CoreNLP's enhanced dependency parser, we also see `:of` attached on the end of `nmod`. Since enhanced is set to `true`, the `of` must be attached to the dependency</br></br>
3. Because the measurement is `10m` we identify it as being an `attached` `measurement_type`</br></br>
4. `"pos_in"` forces the part of speech of the attached node to contain at least one of its keys. In this case, "NN" means the part of speech must be a noun (valid POS tags could be: `NN`, `NNS`, `NNP`, `NNPS`). Since `NN`'s value is null, we are finished and can return resolution as a related word and add it to the output. For some POS tags such as `VB`, we might need to continue traversing edges in the graph, in which case the value could specify a function to be called (e.g. `get_cousin()`)</br>

All such dependency patterns listed in the JSON will be evaluated and if there are any matching patters, they will be added as related words for a measurement.

## API

```shell
extract(content, corenlp, grobid, dependency_patterns_file, output_file=None, show_graph=False, pretty=False, simplify=False)

Returns extracted measurements from a sentence or paragraph.

Parameters: 	content: string
						Sentence or paragraph to extract measurements from.

				corenlp: string
						CoreNLP server endpoint (e.g. "http://localhost:9200"). 

				grobid: string
						Grobid server endpoint (e.g. "http://localhost:8080").

				dependency_patterns_file: string
						Filepath to JSON file containing valid dependency/POS patterns for 
						extracting words and entities related to measurements.

				output_file: string, optional
						File to write extracted measurement output to.

				show_graph: boolean, optional
						If True, a visualization of the dependency and POS network graph 
						will be displayed for each sentence parsed.

				pretty: boolean, optional
						If True, JSON written to file will be indented. If False, one extraction 
						doc per line will be written to the output file

				simplify: boolean, optional 
						If True, only the measurement, unit, and related words of the extracted 
						output will be returned and written to the output file (see 'Output Options' 
						section for more detail).

Returns:		dict: see "Output Options" below
```

## Output Options

#### simple=True

```shell
{"value": 6, "unit": "year", "quantified": {}, "related": {"period": ["study"]}}
```

#### simple=False, pretty=False

```shell
{
	"type": "value",
	"quantity": {
		"parsedValue": 6,
		"rawValue": "six",
		"rawUnit": {
			"offsetStart": 13,
			"offsetEnd": 14,
			"tokenIndices": [
				"3"
			],
			"after": " ",
			"name": "year"
		},
		"offsetEnd": 131,
		"offsetStart": 128,
		"tokenIndex": 24,
		"type": "time"
	},
	"related": [
		{
			"rawName": "period",
			"connector": "",
			"offsetEnd": 21,
			"relationForm": "compound",
			"offsetStart": 15,
			"tokenIndex": 5,
			"descriptors": [
				{
					"rawName": "year",
					"tokenIndex": "4"
				}
			]
		}
	]
}
```

## License
Marve is distributed under [Apache 2.0 license](http://www.apache.org/licenses/LICENSE-2.0).

Contact: Kyle Hundman (<khundman@gmail.com>)

## Acknowledgements

* [Chris Mattmann](http://sunset.usc.edu/~mattmann/), JPL
* Sonny Koliwad, JPL
* Jason Hyon, JPL
* [Ian Colwell](https://github.com/iancolwell), JPL