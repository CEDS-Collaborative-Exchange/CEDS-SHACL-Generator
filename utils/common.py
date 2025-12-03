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

def get_properties_for_class_deep(class_uri, graph):
    """Get properties associated with a class using domainIncludes."""
    properties = []
    # Initialize with properties directly associated with the class
    properties = get_properties_for_class(class_uri, graph)

    # Recursively get properties from parent classes
    class_chain = get_parent_classes(class_uri, graph)
    for parent_class in class_chain:
        properties.extend(get_properties_for_class(parent_class, graph))
        
    # Ensure the list contains unique properties
    return list(set(properties))

def get_parent_classes(class_uri, graph):
    """Get parent classes for a given class URI."""
    parents = set()
    for parent in graph.transitive_objects(URIRef(class_uri), RDFS.subClassOf):
        parents.add(str(parent))
    return parents