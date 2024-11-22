# CEDS-SHACL-Generator
Quickly generate SHACL files for the CEDS Ontology
Initial demonstration where an ontology file is read through RDFLib
and a basic page with Tree of class and properties are displayed as select boxes

### Requirement
python3 installed

### Steps
    - Enable Virtual Environment for python
    ```
        python3 -m venv .venv

    ```

### Activate environment
#### Windows command prompt
```
    .venv\Scripts\activate.bat
```

#### Windows PowerShell
```
.venv\Scripts\Activate.ps1
```

#### macOS and Linux
```
    source .venv/bin/activate
```

## Update pip
```
pip install --upgrade pip
```
### Install packages
This will install listed packages in file requirements.txt 
```
    pip  install -r requirements.txt
```

### Test
There are various python scripts written while learning
RDFLib and its related items

To run a test case inside folder
inside RdfGrapTestContainer.py > function test_query_graph
```
python -m unittest -v test.RdfGrapTestContainer.RdfGrapLearnTest.test_query_graph
 
 ## test > is the folder
 ## RdfGrapTestContainer > name of the module
 ## RdfGrapLearnTest > name of the Test class
 ## test_query_graph > name of test method
```

### Run the streamlit app
```
 streamlit run start_app.py
```

By default the app will open at http://localhost:8501/ or navigate to it

### Deactivate venv
```
deactivate
```