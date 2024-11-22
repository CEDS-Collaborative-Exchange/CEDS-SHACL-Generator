from rdflib import Graph, Namespace, RDF, RDFS, URIRef

# Create an RDF graph
g = Graph()

# Define a custom namespace
EX = Namespace("http://example.org/")

# Bind the namespace for readability in serialized output
g.bind("ex", EX)

# Define an RDF class
person_class = EX.Person
g.add((person_class, RDF.type, RDFS.Class))
g.add((person_class, RDFS.label, URIRef("Person")))

# Define properties for the class
name_property = EX.name
age_property = EX.age

# Add properties as RDF predicates
g.add((name_property, RDF.type, RDF.Property))
g.add((name_property, RDFS.domain, person_class))  # Define the domain as Person
g.add((name_property, RDFS.range, RDFS.Literal))   # Range is a literal value (e.g., string)

g.add((age_property, RDF.type, RDF.Property))
g.add((age_property, RDFS.domain, person_class))  # Define the domain as Person
g.add((age_property, RDFS.range, RDFS.Literal))   # Range is a literal value (e.g., number)

# Add a sample individual to the class
person_instance = EX.JohnDoe
g.add((person_instance, RDF.type, person_class))
g.add((person_instance, name_property, URIRef("John Doe")))
g.add((person_instance, age_property, URIRef("30")))

# Serialize and print the RDF graph in Turtle format
print(g.serialize(format="turtle").decode("utf-8"))