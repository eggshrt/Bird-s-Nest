# OpenAI-first prompt method

The compiler follows the [OpenAI GPT Image prompting guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide): state intended use, keep the structure skimmable, order scene/background then subject, key details, composition/light, and a few constraints, and prefer concrete visible attributes.

v0.4 decisions:

- The final artifact is one Chinese prompt in unlabeled short paragraphs.
- There is no arbitrary character limit. A sentence survives only if it changes a visible outcome or protects a confirmed invariant.
- Camera terms must be paired with visible consequences. Exact focal lengths are guidance, not physics guarantees.
- Positive, concrete descriptions dominate. Only the three highest-value exclusions or invariants may appear at the end.
- Screenplay excerpts never enter the final prompt. At most three short excerpts may appear in a disputed spec summary.
- Pure-environment assets contain no people. References control only the one approved dimension recorded in `ReferenceRoleV1`.
- Do not output headings, alternatives, `negative_prompt`, model parameters, image data, or a second asset.

Asset completeness:

- Character: silhouette, proportion, pose, face/hair, clothing hierarchy, material history, approved bound props, invariant visibility.
- Environment: function, geography, circulation, scale, structure, zone hierarchy, material history, motivated light, pure-environment boundary.
- Hero prop: ownership, dramatic use, handling, scale, mechanism, material weight, causal wear, cultural source, damage state.
