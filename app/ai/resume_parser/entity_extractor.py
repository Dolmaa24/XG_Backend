def extract_entities(text: str) -> dict:
    """Extract person, organisation and location entities via spaCy NER."""
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text)
        entities: dict = {"person": [], "organization": [], "location": []}
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                entities["person"].append(ent.text)
            elif ent.label_ == "ORG":
                entities["organization"].append(ent.text)
            elif ent.label_ == "GPE":
                entities["location"].append(ent.text)
        return entities
    except Exception:
        return {"person": [], "organization": [], "location": []}
