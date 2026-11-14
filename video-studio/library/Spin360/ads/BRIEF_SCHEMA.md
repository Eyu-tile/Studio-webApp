# Brief: extract how each past Spin360 ad was built

Inputs per brief: the brief text (`briefs/<docid>.txt`) and its sheet rows (`brief_rows.json[<docid>]`: the ad IDs made from it,
tab, status, author, editor, concept, avatar, awareness, angle, ad type/variable, whether V1 went to Meta, learnings, feedback).

Output: one JSON object per brief:
{
 "brief_id": "<docid>", "title": "brief's own ad id / name", "ad_ids": ["…"], "n_ads": 0, "uploaded_to_meta": 0,
 "author": "", "editors": [""], "date_hint": "",
 "ad_type": "ideation|iteration|imitation|raw|unclear", "format": "founder-led | UGC testimonial | VSL | educational explainer | skit | AI-generated | mashup | static-like | other",
 "length_hint": "e.g. 30-45s / 60s+ / unknown", "sizes": ["9x16","4x5"],
 "voice": "who speaks (David founder, Vicky, Lauren, AI VO, woman 35-65 …)", "avatar": "", "awareness": "", "angle": "",
 "concept": "1-2 sentences: the idea of the ad",
 "hooks": ["exact hook lines / visual hook descriptions (all variants)"],
 "structure": ["beat-by-beat outline: hook → problem → mechanism → proof → offer → CTA, as the brief lays it out"],
 "key_lines": ["notable script lines, verbatim"],
 "visual_direction": "shots required, b-roll asks, graphics, AI use",
 "tone_music_captions": "tone/feel, music direction, caption style",
 "cta_offer": "e.g. $110 off, shipping, held 7-10 s", "claims": ["claims in the script, verbatim"],
 "assets_referenced": ["named footage/files/folders (e.g. Air_Mixing_Utah.mp4, Kickstart footage, Lauren b-roll)"],
 "iteration_of": "what earlier ad/winner it iterates or imitates, if stated", "learnings_feedback": "from the sheet columns, verbatim-ish",
 "notes": "anything else useful for future ad building"
}
Rules: only what the brief/rows say; quote lines verbatim; empty string/list when absent. Short, concrete. Valid JSON.
