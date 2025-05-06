CEDS/CEPI SHACL Shape Generator Tool

# Overview

This Python tool generates SHACL shape definitions from a list of RDF class and property identifiers. It is designed for use with the CEDS and Extension ontologies and outputs a filtered SHACL file.

# Input Requirements

The script expects a CSV input file containing Class IDs and Property IDs located in the ETL checklist in the following format:  
namespace:ClassID, namespace:PropertyID  
<br/>Each line defines a relationship between a class and a property. The script uses these relationships to build SHACL node and property shapes.

# Functionality

The script performs the following operations:

1. Logging Setup

- Configures a log file to track execution progress and errors.

2. Ontology Initialization

- Loads and parses CEDS and Extension ontology RDF and TTL files into an RDFLib graph.

3. CSV Parsing

- Reads the class-property mappings from the CSV and resolves each identifier to a full URI based on its namespace.

4. SHACL Graph Creation

- Builds a secondary RDF graph where SHACL NodeShapes and PropertyShapes are constructed based on the mappings and class hierarchy.

5. Shape Enrichment

- Adds SHACL-specific constraints such as ignored properties and property ranges. Where applicable, it references parent classes.

6. Output

- The final SHACL file is saved to a temporary location as 'Filtered_SHACL.ttl'.

# File Prompts

The script expects the following files when prompted:

\- Ontology file for the CEDS ontology.

\- Ontology file for the Extension ontology.

\- Input CSV with Class and Property mappings.

\- Extension Namespace

\- Extension Namespace abbreviation

# Output

The tool generates a SHACL file containing NodeShapes and PropertyShapes filtered by the given mappings. The file is saved to:

Filtered_SHACL.ttl

# Execution

The script can be run directly via command line:

python create_shacl.py