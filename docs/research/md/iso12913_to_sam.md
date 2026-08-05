The SAM (Self-Assessment Manikin) measures three dimensions: valence (pleasant–unpleasant), arousal (calm–excited), and dominance (controlled–in-control). The ISO 12913 eight-item circumplex is, by design, two-dimensional — Axelsson's model that the standard codifies projects the eight Likert items onto a circular space whose axes are *pleasantness* (the cosine combination, with pleasant/calm/vibrant on the positive side and annoying/chaotic/monotonous on the negative) and *eventfulness* (the sine combination, eventful/chaotic/vibrant positive, uneventful/calm/monotonous negative). So:

- ISO Pleasantness ↔ SAM Valence — essentially the same construct, both bipolar pleasant/unpleasant, well-correlated in the few studies that have compared them.
- ISO Eventfulness ↔ SAM Arousal — strong conceptual overlap (activation, energy, stimulation), though not identical: eventfulness leans more toward *acoustic density of events* while arousal leans toward *physiological/affective activation*. For most soundscape stimuli these covary closely.
- SAM Dominance — no ISO equivalent. This is the dimension you lose.

The reverse mapping (SAM → ISO eight items) is where it gets lossier. The eight individual items aren't independent — they're points on the circumplex — but they carry semantic flavor that two SAM values can't reconstruct. *Chaotic* and *vibrant* both sit on the high-eventfulness side but on opposite sides of pleasantness; SAM captures that. But *monotonous* vs. *calm* are both low-eventfulness/low-arousal, distinguished mainly by valence — and crucially, *monotonous* carries a negative connotation (boring, unstimulating) that low-arousal-neutral-valence in SAM doesn't naturally express. A genuinely calming soundscape and a tediously dull one can land at similar SAM coordinates.

**Why SAM is still the right choice for your use case**

For a *calming soundscape* objective specifically, you want low arousal and positive valence — and SAM gives you those two cleanly on continuous (typically 9-point) scales rather than as a derived projection from eight Likert items. Three practical advantages: (1) faster ratings per stimulus, which matters a lot if you're collecting data on many candidate mixes; (2) language-independent pictographic format, which sidesteps the translation issues that ISO 12913 has notoriously had across languages; (3) the arousal dimension maps almost directly onto your goal in a way that "pleasantness" alone doesn't — a vibrant carnival can score high-pleasant in ISO terms but is the opposite of what you want.

You can also fold dominance to your advantage: in soundscape work it's been interpreted as *perceived control / non-intrusiveness*, which is actually relevant for calming mixes (a sound that feels like it's bearing down on you is uncalming even at moderate arousal). Most studies discard dominance because it correlates with valence, but for your specific goal it may carry signal worth keeping.

**The pragmatic recommendation**

Collect SAM as your primary instrument and reconstruct an *approximate* ISO Pleasantness for cross-study comparison, rather than trying to reconstruct all eight items. The defensible reconstruction is roughly:

- ISO Pleasantness ≈ linear function of SAM Valence (and possibly a small negative arousal term, since extreme arousal in either valence direction tends to reduce ISO pleasantness)
- ISO Eventfulness ≈ linear function of SAM Arousal
- The individual eight items: don't try. Report SAM, and note that pleasantness/eventfulness coordinates are derivable.

If you want the mapping to be empirically grounded rather than asserted, the cleanest move is a small calibration study: rate ~30–50 stimuli on both instruments and fit the linear transform. That gives you a defensible conversion factor and lets you cite an empirical r² when you claim equivalence. Lam et al. and Mitchell et al. in the soundscape literature have done versions of this; the transforms tend to come out with r > 0.8 on valence/pleasantness and slightly lower on arousal/eventfulness.

One thing to watch: SAM was developed for discrete affective stimuli (images, short sounds, words), and there's some evidence that for *continuous ambient stimuli* of 30+ seconds, raters anchor differently than they do for brief clips. ISO 12913 was purpose-built for 30-second soundscape excerpts. If you go with SAM, standardize your stimulus length and give raters a clear instruction about rating the *overall feeling of being in this sound environment* rather than peak moments, otherwise you'll get noisy data on the arousal axis especially.

## Further Reading

1. [Comparing Soundscape Assessment Methods of ISO 12913-2 with Questionnaires (Methods A and B) and Narrative Interview (Method C)](https://hal.science/hal-03233780/document)

1. [ISO 12913 - Part 1](https://cdn.standards.iteh.ai/samples/52161/229d6f3657604d89b8c382a04058a839/ISO-12913-1-2014.pdf)