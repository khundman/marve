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

from marve import Measurements as m

test = "The patient returned to Europe at 28 weeks of gestation."

coreNLP = "http://localhost:9000"
grobid = "http://localhost:8080"
patterns = "dependency_patterns.json" #default installed with Marve
write_to = "sample_output"

# Pass strings (paragraph at most)
m.extract(test, coreNLP, grobid, patterns, write_to, show_graph=False, pretty=True, simplify=False)

