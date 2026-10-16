# Visual concept design method

The purpose is a single source of truth that another human or downstream Skill can execute without inventing the missing creative direction. Use independent wording; this is not a reproduction of any course text.

## Shared dimensions

Close these branches for every asset:

- dramatic function and target audience perception;
- core proposition and relationship to the whole-work arc;
- world, region, culture, institution, era, and realism boundaries;
- one design direction and its visual grammar;
- primary recognition anchor plus supporting concrete elements;
- silhouette/space, color/value hierarchy, material, weight, wear, and environmental interaction;
- one primary state and approved derived-state deltas;
- invariants, continuity, forbidden defaults, and cultural exclusions;
- intended use, aspect ratio, production feasibility, references, and observable acceptance criteria.

Register resolved dimensions directly; do not turn every item into a mandatory interview question. Consequential unresolved dimensions remain open and block approval. A non-applicable dimension uses `{"status": "not_applicable", "reason": "specific reason"}`; empty strings, null values, and unexplained placeholders do not resolve it.

Each user reference needs one or more `controls` and one or more `must_not_control` entries. A reference never silently controls identity, costume, material, pose, composition, palette, lighting, and style at once.

## Character master

- dramatic role, core proposition, relationship system, and selected growth stage;
- physiology, age impression, body proportion, weight distribution, posture, and action line;
- primary/secondary shape language, silhouette, negative space, and movement readability;
- facial structure, skin history, hair, grooming, makeup, and deliberate self-presentation;
- clothing structure and layers: intimate, functional, identity, protection, and personal modification;
- wearing behavior, class/profession/institution signals, palette, material, wear, and visible weight;
- bound props, recurring motifs, one primary memory point, and two or fewer secondary recognition points;
- canonical invariants and derived changes for pressure, injury, status, disguise, or arc stage.

Reject stereotype-to-costume shortcuts. Externalize personality through repeated behavior, posture, selection, maintenance, adaptation, and use history.

## Location master

- story function, emotional property, geography, climate, era, and cultural/institutional ownership;
- scale, approach, circulation, thresholds, zones, sightlines, usable negative space, and movement paths;
- construction logic, architecture, infrastructure, practical light sources, weather response, and damage;
- inhabitants' routines, maintenance, signage, storage, security, hierarchy, and evidence of use;
- value/color/material system and primary recognition anchors;
- reusable invariants plus approved time, weather, occupation, damage, and narrative-state deltas.

Reject attractive architecture that does not explain how people live, work, move, control access, or leave traces. The downstream image requirement uses `output_scope: pure_environment`; occupants may explain traces of use without becoming visible subjects.

## Scene state

- exact versioned `location_master` in `dependency_assets` using `ref_asset_id`, its requirement path/hash, and screenplay scene/beat ids;
- dramatic purpose, selected moment, audience information, participants, and power relation;
- spatial changes from the location master, blocking zones, attention hierarchy, must-see and must-hide information;
- time, weather, atmosphere, motivated light, environmental motion, and physical interaction;
- entry/exit continuity, change from the master, and what must reset or persist afterward;
- production complexity and a simpler fallback that preserves dramatic intent.

The accepted output is a pure-environment state of one scene with `output_scope: pure_environment`. Participants, power relations, and dramatic purpose are context for environmental choices. The location master is a read-only dependency, not a second creative subject.

When the requested output depicts participants, performance, or dramatic blocking, preserve that intent and route it to `$screenplay-scene-daoyanzu`. Only produce an environment-only extraction from such a request after the user explicitly chooses that reduced scope. This contract does not produce shot lists or generation prompts.

## Hero prop

- owner/custodian, dramatic function, history, reveal/payoff, and relationship to character behavior;
- scale, grip, operation, interface, construction, mechanism, balance, and visible weight;
- material origin, manufacture/repair logic, wear map, contamination, damage, and environmental response;
- cultural/institutional meaning, primary recognition anchor, motif relation, and counterfeit/cliché risks;
- intact primary state and approved used, damaged, transformed, transferred, or depleted deltas;
- interaction, continuity, safety, replacement, and production feasibility.

Reject ornament whose meaning cannot be supported by ownership, use, culture, or story consequence.
