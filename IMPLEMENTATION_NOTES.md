# CEDS SHACL Generator - Class Hierarchy Selection Feature

## Overview

This implementation adds support for handling `rangeIncludes` selection when there are multiple rangeIncludes values, particularly when dealing with parent/child class hierarchies.

## Requirements Implemented

Based on `requirements.md`, the following features have been implemented:

1. **Parent Class Detection**: The system automatically detects when an object property's rangeIncludes points to a parent class (a class that has child classes).

2. **Multi-Select UI for Class Hierarchy**: When a parent class is detected, a multiselect dropdown appears allowing users to choose which classes (parent and/or children) should be allowed in the SHACL constraints.

3. **SHACL Output with sh:or**: When multiple classes are selected, the generated SHACL uses the `sh:or` construct to allow any of the selected classes.

4. **Single Class Handling**: When a non-parent class is detected or when only one class is selected, the system automatically uses that class directly with `sh:class`.

## Architecture

### New Helper Functions (utils/common.py)

```python
def is_parent_class(class_uri, graph) -> bool
```
- Checks if a class has any child classes
- Returns True if the class is referenced in any `rdfs:subClassOf` statement

```python
def get_child_classes(class_uri, graph) -> Set[str]
```
- Recursively finds all direct and indirect child classes
- Returns a set of URIs for all descendants

```python
def get_class_hierarchy(class_uri, graph) -> List[Dict]
```
- Builds complete hierarchy including parent and all children
- Returns list of dicts with 'uri', 'label', and 'is_parent' keys

### Modified Components

#### 1. Property Selection UI (_render_class_properties_fragment)

**Location**: `utils/SHACL.py`, lines ~1110-1270

**Changes**:
- Added check for object properties with class ranges
- Detects parent classes using `is_parent_class()`
- Displays multiselect widget for parent class hierarchies
- Stores user selections in `st.session_state.property_class_selections`

**Session State Key Format**: `"{class_uri}::{property_uri}"`

**Example Output**:
```python
st.session_state.property_class_selections = {
    "http://ceds.ed.gov/terms#C200208::http://ceds.ed.gov/terms#P600549": [
        "http://ceds.ed.gov/terms#C200239",  # Organization (parent)
        "http://ceds.ed.gov/terms#C200074",  # Course Section (child)
        "http://ceds.ed.gov/terms#C200315"   # Another child
    ]
}
```

#### 2. SHACL Generation (create_property_shapes)

**Location**: `utils/SHACL.py`, lines ~518-630

**Changes**:
- Checks for user-selected classes in `property_class_selections`
- Generates `sh:or` construct when multiple classes are selected
- Each class in the OR list is wrapped in a blank node with `sh:class`
- Automatically adds `sh:node` if any selected class is being expanded
- Falls back to `sh:nodeKind sh:BlankNodeOrIRI` for IRI-only references

## Generated SHACL Examples

### Multiple Classes Selected (sh:or construct)

When user selects multiple classes from a hierarchy:

```turtle
cepi:hasK12StaffAssignmentOrganizationShape a sh:PropertyShape ;
    sh:or (
        [ sh:class ceds:C200239 ]  # Organization (parent)
        [ sh:class ceds:C200074 ]  # Course Section (child)
        [ sh:class ceds:C200315 ]  # Another child
    ) ;
    sh:node ceds:OrganizationShape ;
    sh:nodeKind sh:BlankNodeOrIRI ;
    sh:path ceds:P600062 .
```

### Single Class (No Parent/Children)

When property points to a class without children:

```turtle
ceds:hasMembershipRelationshipShape a sh:PropertyShape ;
    sh:class ceds:C200207 ;
    sh:node ceds:MembershipShape ;
    sh:path ceds:P600549 .
```

### Single Class from Hierarchy

When user selects only one class from a parent class hierarchy:

```turtle
ceds:hasMembershipRelationshipShape a sh:PropertyShape ;
    sh:class ceds:C200208 ;
    sh:node ceds:K12StaffAssignmentShape ;
    sh:path ceds:P600549 .
```

## User Workflow

1. **Navigate to "Class and Property Menu"**
   - Load the CEDS ontology (auto-loaded from `data/CEDS-Ontology.rdf`)
   - Expand a class to see its properties

2. **Select Properties**
   - Check the checkbox for properties you want to include
   - For object properties with parent class ranges, a multiselect dropdown appears

3. **Choose Classes (for parent classes only)**
   - Select one or more classes from the hierarchy
   - Default selection is the parent class
   - Can select any combination of parent and child classes

4. **Generate SHACL**
   - Navigate to "SHACL" page
   - Click "Generate SHACL"
   - The output will include `sh:or` constructs for multi-class selections

## Technical Details

### Session State Variables

- `class_property_map`: Dict[str, Set[str]] - Maps class URIs to selected property URIs
- `property_class_selections`: Dict[str, List[str]] - Maps "{class}::{property}" to list of selected class URIs

### Detection Logic

```python
# Check if range is a class (not datatype, not option set)
ranges = list(graph.objects(URIRef(prop_uri), SDO.rangeIncludes))

for range_uri in ranges:
    # Skip datatypes
    if str(range_uri).startswith(str(XSD)):
        continue
    
    # Skip option sets (concept schemes)
    option_set = list(graph.subjects(RDF.type, URIRef(range_uri)))
    if len(option_set) > 0:
        continue
    
    # Check if it's a class
    classes = list(graph.subjects(RDF.type, RDFS.Class))
    if range_uri in classes:
        # Check if parent class
        if is_parent_class(str(range_uri), graph):
            # Show multiselect UI
```

### RDF/SHACL Generation

The `sh:or` construct is created using RDFLib's `Collection`:

```python
# Create blank nodes for each class
or_list = []
for class_uri in selected_classes:
    class_node = BNode()
    g.add((class_node, SH["class"], URIRef(class_uri)))
    or_list.append(class_node)

# Create the collection
or_collection = BNode()
Collection(g, or_collection, or_list)
g.add((prop_shape, SH["or"], or_collection))
```

## Testing

A test script is provided to verify the helper functions:

```bash
python test_class_hierarchy.py
```

This tests:
- Parent class detection
- Child class enumeration
- Full hierarchy building
- Label extraction

## Notes and Considerations

1. **Performance**: Class hierarchy detection is efficient using RDFLib's graph queries
2. **UI Updates**: The multiselect appears/disappears dynamically as properties are checked/unchecked
3. **Default Behavior**: If no classes are explicitly selected, the system uses the rangeIncludes class as before
4. **Backward Compatibility**: Existing functionality for datatypes, option sets, and simple class references is preserved

## Future Enhancements

Possible improvements for future versions:
- Visual tree representation of class hierarchies
- Bulk selection options (e.g., "Select all children")
- Hierarchical indentation in multiselect to show parent/child relationships
- Caching of hierarchy data for large ontologies
- Export/import of class selections for reuse
