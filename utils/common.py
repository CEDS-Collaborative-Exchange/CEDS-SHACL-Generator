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

def get_child_classes(class_uri, graph):
    """Get all direct and indirect child classes for a given parent class URI.
    
    Args:
        class_uri: URI of the parent class
        graph: RDF graph containing the ontology
        
    Returns:
        Set of URIs (as strings) for all child classes
    """
    children = set()
    for child in graph.subjects(RDFS.subClassOf, URIRef(class_uri)):
        child_str = str(child)
        children.add(child_str)
        # Recursively get children of children
        children.update(get_child_classes(child_str, graph))
    return children

def is_parent_class(class_uri, graph):
    """Check if a class is a parent class (has at least one child class).
    
    Args:
        class_uri: URI of the class to check
        graph: RDF graph containing the ontology
        
    Returns:
        Boolean indicating whether the class has children
    """
    # Check if any class has this class as rdfs:subClassOf
    for _ in graph.subjects(RDFS.subClassOf, URIRef(class_uri)):
        return True
    return False

def get_class_hierarchy(class_uri, graph):
    """Get the complete class hierarchy including the parent and all its children.
    
    Args:
        class_uri: URI of the class
        graph: RDF graph containing the ontology
        
    Returns:
        List of dicts with 'uri', 'label', and 'is_parent' for each class in hierarchy
    """
    hierarchy = []
    
    # Add the parent class itself
    parent_label = get_label(class_uri, graph)
    hierarchy.append({
        'uri': class_uri,
        'label': parent_label,
        'is_parent': True
    })
    
    # Add all child classes
    children = get_child_classes(class_uri, graph)
    for child_uri in sorted(children):
        child_label = get_label(child_uri, graph)
        hierarchy.append({
            'uri': child_uri,
            'label': child_label,
            'is_parent': False
        })
    
    return hierarchy