from rdflib import Namespace, URIRef, RDFS

def get_rdf_format(file_name):
    """Determine the RDF format based on the file extension."""
    formats = {".ttl": "turtle", ".rdf": "xml", ".xml": "xml"}
    extension = file_name.lower().split(".")[-1]
    return formats.get(f".{extension}", None)  # Ensure the extension is prefixed with a dot

def add_namespace(namespaces, prefix, uri):
    """Add a namespace to the namespaces dictionary."""
    if prefix not in namespaces:
        namespaces[prefix] = Namespace(uri)

def get_label(uri, graph):
    """Get the human-readable label for a URI."""
    label = next(graph.objects(URIRef(uri), RDFS.label), None)
    return str(label) if label else str(uri)

def get_properties_for_class(class_uri, graph):
    """Get properties associated with a class using domainIncludes."""
    properties = []
    for prop in graph.subjects(Namespace("https://schema.org/").domainIncludes, URIRef(class_uri)):
        properties.append(prop)
    return properties
