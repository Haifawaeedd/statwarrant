# Sentence-selection rule (fixed before collection)

**Date fixed:** 2026-11-16 · **Applies to:** pilot (30 sentences) and main study (100–150 new sentences, none from the pilot)

## The rule (one line)

> Include the first sentence in the Results or Discussion section of each CC-BY article found by the fixed PubMed Central search below, taken in the order the results are listed, that makes a comparative claim about an effect and reports its estimate with an SE or CI in the same or adjacent sentence; take at most 3 sentences per article and at least 6 sentences from each of 5 fields.

## Fixed searches (PubMed Central, https://pmc.ncbi.nlm.nih.gov)

Use one search per field, exactly as written, and record the date you ran it.

| Field | Search |
|---|---|
| Clinical medicine | `"randomized" AND "confidence interval" AND cc by license[filter]` |
| Public health / epidemiology | `"cohort" AND "confidence interval" AND cc by license[filter]` |
| Psychology | `"psychology" AND "confidence interval" AND cc by license[filter]` |
| Education | `"students" AND "education" AND "confidence interval" AND cc by license[filter]` |
| Nutrition / exercise science | `("diet" OR "exercise") AND "confidence interval" AND cc by license[filter]` |

Add the publication-year limit `AND 2025[pdat]` for the pilot. For the main study use `AND 2024[pdat]` so no article can overlap with the pilot.

## Procedure

1. Run the search for one field. Save a screenshot or export of the result list with the date.
2. Open the results in the order listed. For each article:
   - Check that the licence shown on the article page is **CC BY**. If not, skip it and note why.
   - Read the Results section, then the Discussion section, from the top.
   - Take the **first** sentence that (a) claims something about an effect or a difference and (b) has its estimate with an SE or CI in the same or the next sentence.
   - Take up to 3 such sentences from one article, then move to the next article.
3. Stop when the field has 6 sentences (pilot). Repeat for the other fields.
4. Record every skipped article and the reason, so the selection can be checked.

## What not to do

- Do not choose sentences because you think statwarrant will get them right or wrong.
- Do not run statwarrant on a sentence before both reviewers' labels are locked.
- Do not edit the sentence text; copy it exactly.
- If the rule turns out to be unclear, write the problem down and fix the rule **before** collecting more sentences; never fix it after seeing results.
