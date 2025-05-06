# Overview
This document serves as an entry point to users tasked with the creation of SHACL documents for the purpose of supporting CEPI data collection. This includes identifying the inputs, the outputs and the means for translating between the two. Additionally, an abbreviated background overview of major concepts is also provided.

# Workflow
As shown below, the path to generating SHACL file(s) that will ensure data are collected in a consistent and accurate manner requires several steps.

![Ontology to SHACL Workflow](./CEDS_Ontology_to_SHACL_workflow.png "SHACL Generation Workflow")

| Workflow Item                       | Description | Example / URL  |
|-------------------------------------|-------------|----------------|
| `CEDS Ontology`                     | The CEDS ontology is the logical definition of the CEDS data model in RDF XML format. It includes fundamental concepts like a Person with a Name, as well as specific elements like gender.    | [CEDS open-source community](https://github.com/CEDStandards/CEDS-Ontology), [Self-hosted version](https://dev.cepi.state.mi.us/Ontology/ceds-ontology.rdf) |
| `ETL Checklist`                     | Education authorities extend the CEDS data model by aligning fields from legacy systems to CEDS specifications. These extensions can be specified in an ETL checklist and translated to SHACL. | — |
| `CEPI Extension Ontology Generator` | Converts ETL Checklist rows and columns into RDF XML format for the CEPI Ontology using a small Python application.                                                                            | [CEPI Extension Ontology Generator](https://dev.azure.com/SOM-MDECEPI/MiSchool.DataModernization/_git/CEDS%20Data%20Warehouse?path=/SHACL/CEPI%20Extension%20Ontology%20Generator) |
| `CEPI Ontology`                     | Custom nodes and properties for a state education authority are generated as a stand-alone file for flexibility.                                                                               | [Person class extension](https://dev.cepi.state.mi.us/Ontology/cepi-ontology/Person_Ontology_Extension.ttl) |
| `CEPI SHACL Generator`              | Translates an RDF XML ontology to SHACL format through prescribed rules and mappings, encapsulated in a Python-based tool.                                                                     | [CEPI SHACL Generator](https://dev.azure.com/SOM-MDECEPI/MiSchool.DataModernization/_git/CEDS%20Data%20Warehouse?path=/SHACL/SHACL%20Generator) |
| `CEDS & CEPI Node SHACL`            | Identifies foundational elements to be collected, such as a person’s name and gender, based on the CEDS or CEPI ontology using the CEPI SHACL Generator.                                       | — |
| `CEDS SHACL Generator`              | A separate working group developed a PHP-based tool to translate CEDS ontology properties into the SHACL format.                                                                               | [CEDS SHACL Generator](https://github.com/opensalt/CEDS-shacl-generator) |
| `CEDS Property SHACL`               | Defines specific fields and option sets needed for a physical data model, translated from the CEDS ontology to SHACL format.                                                                   | [Self-hosted properties file](https://dev.cepi.state.mi.us/Ontology/PropertyShapes.ttl) |

# Background
Data can be structured and moved in countless formats, but the JSON format has become one of the more popular options. Its relatively simple format (it is comprised of 6 primary data types) has facilitated widespread adoption within software and API development. There are, however, use cases such as the collection of administrative data that require the imposition of additional structure. This is where JSON for Linked Data, or JSON-LD, enters. JSON-LD allows the connection of JSON data to data model specifications. This data model allows for the definition of complex rulesets to govern the content of JSON-LD files. As should be expected, there are multiple standards available to define the data model that will govern JSON-LD content. The Shapes Constraint Language (SHACL) is particularly useful because it enables explicit data validation logic such as required fields or formats. 

> TLDR: Administrative data can be stored in the JSON-LD format. SHACL can be used to ensure data validity.

# Terminology
Storing data and validation logic in new formats introduces new terminology and new synonyms. Using the proposed terms, below, will facilitate improved communication.

| Proposed Term  | RDF XML Ontology    | SHACL Ontology                 | Database Analog  | Example              | Notes                                                                                                          |
|----------------|---------------------|--------------------------------|------------------|----------------------|----------------------------------------------------------------------------------------------------------------|
| Class          | rdfs:Class          | nodeShape                      | Table            | Organization         | Classes may have subclasses; almost all classes have a parent class.                                           |
| Property       | rdf:property        | propertyShape (Dates/Literals) | Field            | Organization Name    | Properties of base type (string, date/time, etc.)                                                              |
| Property       | rdf:property        | propertyShape (IRI)            | Foreign Key      | Organization Type    | Properties that point to a class (of type IRI/node)                                                            |
| Option Value   | owl:NamedIndividual | In Constraint                  | value choice     | K12School, LEA, etc. | Each value effectively defines one of the choices that would for instance appear in a dropdown control in a UI |


# Abridged Example

The fundamental starting point for building CEDS-compliant SHACL is, of course, the CEDS Ontology. The CEDS ontology is itself a data specification. It allows us to infer relationships between data elements (e.g., a person has a first name) but it doesn't enforce validation rules (e.g., a first name has a length limit). Although it doesn't follow the SHACL standard, it can be translated to SHACL programmatically and validations such as required fields can be amended to enhance the SHACL. Here's the representation of First Name in the CEDS ontology:

```
<rdf:Property rdf:about="http://ceds.ed.gov/terms#P000115">
	<dc:creator>Common Education Data Standards</dc:creator>
	<dc:identifier rdf:datatype="http://www.w3.org/2001/XMLSchema#token">P000115</dc:identifier>
	<rdfs:label>First Name</rdfs:label>
	<schema:domainIncludes rdf:resource="http://ceds.ed.gov/terms#C200377"/>
	<schema:rangeIncludes rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
	<skos:notation>FirstName</skos:notation>
</rdf:Property>
```
And here is First Name represented in the SHACL format with an included length constraint:

```
ceds:P000115Shape
  a sh:PropertyShape ;
  sh:path ceds:P000115;
  sh:name "First Name" ;
  sh:datatype xsd:normalizedString ;
  sh:maxLength 35 ; 
.
```
Given the above SHACL structure, a simplified version of a JSON-LD document for a person might take this form:

```json
{
    "@type": "Person",
    "@id": "http://cepi.michigan.gov/person/38330",
	
    "hasPersonName": {
        "@type": "PersonName",
        "FirstName": "Susan",
        "LastOrSurname": "Anthony"
    }
}
```
In this example the SHACL file uses a coded indicator for first name (P000115) whereas the JSON-LD file uses a descriptive indicator (FirstName). This increases the human-readability of the JSON-LD files but does require provision of a crosswalk for the terms. An intermediary "context" file is used to map elements of a JSON-LD file to the corresponding element in the SHACL document. While technically out-of-scope for this documentation, users can [access it online](https://dev.cepi.state.mi.us/Ontology/context.json). This context file is also in JSON format:

```json
{
    "@context": {
        "@base": "http://ceds.ed.gov/terms#",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "ceds": "http://ceds.ed.gov/terms#",
        "FirstName": "P000115"
	}
}
```
