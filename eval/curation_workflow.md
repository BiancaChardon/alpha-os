# Headline Curation Workflow (Scott)

1. **Sources monitored daily**
   - EIA Today in Energy RSS
   - FERC eLibrary notices (fixture or search API)
   - OPEC press releases

2. **Inclusion criteria**
   - Mentions power, gas, crude, pipeline, ISO, curtailment, sanctions, or regulatory action
   - Published within the last 48 hours
   - Not a duplicate of an existing headline URL/hash

3. **Curation steps**
   - Fetch raw headlines via adapters
   - Normalize text and compute `text_hash`
   - Drop duplicates by URL/hash
   - Tag commodity relevance manually for ambiguous items during weekly review
   - Add curated fixture entries when live source is unavailable for demo reliability

4. **Quality checks**
   - Every curated headline must include title, URL, and at least one sentence summary
   - FERC entries should include docket when available
   - OPEC entries should note whether the release is production policy or geopolitical commentary

5. **Handoff to ingestion agent**
   - Curated items are stored as `SignalEvent(modality='text')`
   - Ingestion agent assigns urgency/sentiment before synthesis
