# Frozen clean512_v2 numeric CTC diagnostic audit

Evaluation only, using **train + validation**. No training, fine-tuning, frozen-artifact modifications, decoder tuning, test inference, integration, commit or push. This is descriptive evidence, not clinical readiness or a proven training-regression cause.

## Verification and protocol

Checkpoint SHA-256 `c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b` verified before and after inference. All 1,005 clean-corpus files match the frozen snapshot; corpus/checkpoint/sidecar hashes remain unchanged. Every in-memory model weight is byte-identical before/after inference (including batch-normalization state). Input64×512×1; logits128×49; padding0; blank48; labels1–47. Softmax is across classes per frame. Both production greedy and locked ordinary beam50 are unchanged; diagnostic top5 uses the same width50 and top1 equality is asserted.

**Vocabulary limitation:** digits8 and9 are absent from the frozen vocabulary. Their trace probabilities/IDs are null, not remapped. No conclusions about recognizing them are possible.

|Symbol|ID|
|---|---|
|' '|1|
|'-'|2|
|'0'|3|
|'1'|4|
|'2'|5|
|'3'|6|
|'4'|7|
|'5'|8|
|'6'|9|
|'7'|10|
|'A'|11|
|'B'|12|
|'C'|13|
|'D'|14|
|'H'|15|
|'I'|16|
|'M'|17|
|'N'|18|
|'O'|19|
|'P'|20|
|'Q'|21|
|'R'|22|
|'S'|23|
|'T'|24|
|'a'|25|
|'b'|26|
|'c'|27|
|'d'|28|
|'e'|29|
|'f'|30|
|'g'|31|
|'h'|32|
|'i'|33|
|'j'|34|
|'l'|35|
|'m'|36|
|'n'|37|
|'o'|38|
|'p'|39|
|'r'|40|
|'s'|41|
|'t'|42|
|'u'|43|
|'w'|44|
|'x'|45|
|'y'|46|
|'z'|47|

Deterministic full-target Viterbi alignment and exact forward target-sequence probability are diagnostics only. They never alter predictions. Assigned peaks are target-constrained, not calibrated character confidence; a forced path can assign a very improbable frame. Probability sums across assigned frames are not sequence probabilities. Full-line Levenshtein projection can ambiguously allocate identical symbols/spaces at token boundaries. Tables retain this caveat.

## Train and validation findings

|Split|N|CER|WER|Exact line|
|---|---|---|---|---|
|train|700|0.035152|0.098998|0.344286|
|validation|100|0.11294|0.249288|0.05|

All800 train/validation lines were inferred for character-conditioned statistics and saved as raw logits + full normalized posteriors. Detailed cohort: 643 unique lines; schedules 298, durations 553. Every cohort row retains renderer/font/fitting/bounds/target/decoder/alignment lengths.

## Schedule error matrix

|Split|N|Beam correct|Greedy correct|Digit deleted|Digit substituted|Hyphen deleted|Prefix deleted|Suffix deleted|Multiple deletions|
|---|---|---|---|---|---|---|---|---|---|
|train|263|153|124|115|9|107|24|64|106|
|validation|35|26|22|6|3|5|4|1|5|

|Split|Target|Projected beam token|Count|
|---|---|---|---|
|train|1-1-1|'1-1'|53|
|train|1-0-1|'1-0-1'|49|
|train|0-0-1|'0-0-1'|39|
|train|1-0-0|'1-0-0'|37|
|train|0-1-0|'0-1-0'|23|
|train|0-1-0|'0-1'|12|
|train|0-1-0|'0-0'|9|
|train|1-0-1|'0-1'|8|
|train|0-0-1|'0-1'|7|
|train|1-0-0|'0-1'|6|
|train|1-1-1|'1-1-1'|5|
|train|0-0-1|'-1'|3|
|train|1-1-1|'-1'|3|
|train|0-0-1|'1-1'|2|
|train|1-1-1|'1-1 '|2|
|train|0-1-0|' 0-1-0'|1|
|train|1-0-0|'1-0'|1|
|train|1-0-1|'-1'|1|
|train|1-0-1|'1-1'|1|
|train|1-1-1|' 1-1'|1|
|validation|0-1-0|'0-1-0'|8|
|validation|1-0-0|'1-0-0'|7|
|validation|0-0-1|'0-0-1'|5|
|validation|0-1-0|'0-1-1-0'|3|
|validation|1-0-1|'1-0-1'|3|
|validation|1-1-1|'1-1-1'|3|
|validation|1-1-1|'1-1'|2|
|validation|1-0-0|' -1'|1|
|validation|1-0-0|'0-1'|1|
|validation|1-0-1|' 1-0-1'|1|
|validation|1-1-1|'-1'|1|

## Duration error matrix

|Split|N|Beam correct|Greedy correct|Digit deleted|Digit substituted|Hyphen deleted|Prefix deleted|Suffix deleted|Multiple deletions|
|---|---|---|---|---|---|---|---|---|---|
|train|493|316|315|113|63|0|0|0|113|
|validation|60|33|33|8|18|0|0|0|8|

|Split|Target|Projected beam token|Count|
|---|---|---|---|
|train|x 5d|'x 5d'|99|
|train|x 3d|'x 3d'|98|
|train|for 7 days|'for days'|61|
|train|x 7d|'x 3d'|60|
|train|for 5 days|'for days'|52|
|train|for 5 days|'for 5 days'|48|
|train|for 7 days|'for 7 days'|48|
|train|x 7d|'x 7d'|23|
|train|x 7d|' x 3d'|2|
|train|for 7 days|'for f days'|1|
|train|x 3d|' x 3d'|1|
|validation|x 7d|'x 3d'|12|
|validation|x 3d|'x 3d'|11|
|validation|x 5d|'x 5d'|8|
|validation|for 5 days|'for 5 days'|6|
|validation|for 7 days|'for 7 days'|6|
|validation|for 5 days|'for days'|5|
|validation|x 5d|'x 3d'|5|
|validation|for 7 days|'for days'|3|
|validation|x 7d|'x 7d'|2|
|validation|for 5 days|'for 5 ays'|1|
|validation|for 7 days|'fofor days'|1|

## Forced alignment, digit/hyphen posteriors and position

|Group|N|Assigned peak mean|Median|Local peak mean|Assigned weak<.1|Local weak<.1|Local nonargmax|
|---|---|---|---|---|---|---|---|
|duration/train/correct/numeral|316|0.8441|0.8868|0.8441|0.0|0.0|0.003|
|duration/train/incorrect/numeral|177|0.1338|0.0461|0.1353|0.621|0.621|0.983|
|duration/validation/correct/numeral|33|0.8123|0.8079|0.8123|0.0|0.0|0.0|
|duration/validation/incorrect/numeral|27|0.2309|0.245|0.2386|0.296|0.296|0.963|
|schedule/train/correct/final_digit|153|0.9945|0.9968|0.995|0.0|0.0|0.0|
|schedule/train/correct/first_digit|153|0.9884|0.9927|0.9884|0.0|0.0|0.0|
|schedule/train/correct/first_hyphen|153|0.9876|0.9935|0.9887|0.0|0.0|0.0|
|schedule/train/correct/middle_digit|153|0.7885|0.8884|0.8113|0.0|0.0|0.163|
|schedule/train/correct/second_hyphen|153|0.9668|0.9842|0.9734|0.0|0.0|0.0|
|schedule/train/incorrect/final_digit|110|0.7785|0.9888|0.7785|0.0|0.0|0.164|
|schedule/train/incorrect/first_digit|110|0.6858|0.9478|0.6858|0.0|0.0|0.245|
|schedule/train/incorrect/first_hyphen|110|0.9422|0.976|0.9485|0.0|0.0|0.0|
|schedule/train/incorrect/middle_digit|110|0.1387|0.1391|0.6228|0.273|0.009|0.364|
|schedule/train/incorrect/second_hyphen|110|0.6312|0.5547|0.9294|0.0|0.0|0.0|
|schedule/validation/correct/final_digit|26|0.9941|0.9954|0.9941|0.0|0.0|0.0|
|schedule/validation/correct/first_digit|26|0.9867|0.9895|0.9867|0.0|0.0|0.0|
|schedule/validation/correct/first_hyphen|26|0.9836|0.9948|0.9867|0.0|0.0|0.0|
|schedule/validation/correct/middle_digit|26|0.7181|0.8438|0.7645|0.0|0.0|0.154|
|schedule/validation/correct/second_hyphen|26|0.9167|0.9747|0.9555|0.0|0.0|0.0|
|schedule/validation/incorrect/final_digit|9|0.7317|0.7644|0.7317|0.0|0.0|0.222|
|schedule/validation/incorrect/first_digit|9|0.6201|0.4332|0.6201|0.0|0.0|0.333|
|schedule/validation/incorrect/first_hyphen|9|0.9823|0.9766|0.9823|0.0|0.0|0.0|
|schedule/validation/incorrect/middle_digit|9|0.4049|0.1285|0.6451|0.222|0.0|0.222|
|schedule/validation/incorrect/second_hyphen|9|0.7315|0.5822|0.9633|0.0|0.0|0.0|

The ±3-frame local window is a declared sensitivity check around forced assignment; it can include another occurrence of the same symbol. Nonargmax measures direct competition, not decoder culpability. Each duration character includes simultaneous digit/hyphen/space probabilities at its assigned peak, neighboring blanks, word emissions and full target-sequence log probability in token_details.json. Full traces/raw arrays allow independent inspection.

## Repeated symbols and blank separation

The three digits of1-1-1 are separated by hyphens: **none is an adjacent identical CTC repeat**. Likewise the zeros in1-0-0 are not adjacent CTC repeats. No blank is mathematically required between a digit and hyphen or hyphen and digit. Actual adjacent identical labels elsewhere in a line do require a separating blank and are handled by the alignment algorithm. A zero-frame blank gap inside a schedule is not automatically an error.

|Pattern/group|Pairs|Mean first peak|Mean later peak|Mean distance|Mean blank-dominant frames|Mean peak blank|
|---|---|---|---|---|---|---|
|0-0-1/correct/first_digit→middle_digit|44|0.9952|0.8448|5.43|0.0|0.0|
|0-0-1/incorrect/first_digit→middle_digit|12|0.3943|0.0538|10.42|0.0|0.0011|
|0-1-0/correct/first_digit→final_digit|31|0.9955|0.9976|10.9|0.0|0.0|
|0-1-0/incorrect/first_digit→final_digit|25|0.6953|0.5955|11.88|0.0|0.0006|
|1-0-0/correct/middle_digit→final_digit|44|0.9378|0.9933|5.16|0.0|0.0|
|1-0-0/incorrect/middle_digit→final_digit|9|0.052|0.2478|2.11|0.0|0.0001|
|1-0-1/correct/first_digit→final_digit|52|0.9816|0.994|10.71|0.0|0.0|
|1-0-1/incorrect/first_digit→final_digit|11|0.3844|0.7433|13.27|0.0|0.0012|
|1-1-1/correct/first_digit→final_digit|8|0.9891|0.9964|12.75|0.0|0.0|
|1-1-1/correct/first_digit→middle_digit|8|0.9891|0.2697|7.88|0.0|0.0|
|1-1-1/correct/middle_digit→final_digit|8|0.2697|0.9964|4.88|0.0|0.0|
|1-1-1/incorrect/first_digit→final_digit|62|0.8285|0.9321|10.16|0.0|0.0004|
|1-1-1/incorrect/first_digit→middle_digit|62|0.8285|0.1761|7.05|0.0|0.0004|
|1-1-1/incorrect/middle_digit→final_digit|62|0.1761|0.9321|3.11|0.0|0.0|

## Character-conditioned statistics

|Character/context/line|N|Peak mean|Median|p10|p25|Mean span|Weak<.1|Nonargmax|
|---|---|---|---|---|---|---|---|---|
|'-'|596|0.9009|0.9779|0.5532|0.9203|3.441|0.0|0.023|
|'-/correct_line'|164|0.9775|0.9904|0.9478|0.9785|2.915|0.0|0.0|
|'-/incorrect_line'|432|0.8718|0.9757|0.5348|0.8489|3.641|0.0|0.032|
|'-/schedule'|596|0.9009|0.9779|0.5532|0.9203|3.441|0.0|0.023|
|'0'|1081|0.8895|0.9949|0.6763|0.9071|2.117|0.027|0.071|
|'0/correct_line'|350|0.9464|0.9947|0.8151|0.9228|2.171|0.0|0.003|
|'0/dose_digit'|688|0.9385|0.9976|0.771|0.9561|2.225|0.0|0.022|
|'0/incorrect_line'|731|0.8622|0.9953|0.3516|0.889|2.092|0.04|0.104|
|'0/schedule'|393|0.8036|0.9525|0.1477|0.8493|1.929|0.074|0.158|
|'1'|610|0.7815|0.9859|0.1966|0.5203|1.908|0.007|0.228|
|'1/correct_line'|140|0.9144|0.9919|0.4336|0.9789|2.114|0.0|0.114|
|'1/dose_digit'|109|0.9741|0.9948|0.97|0.9861|1.927|0.009|0.009|
|'1/incorrect_line'|470|0.7419|0.9798|0.1625|0.3623|1.847|0.009|0.262|
|'1/schedule'|501|0.7396|0.9794|0.1702|0.3607|1.904|0.006|0.275|
|'3'|110|0.7359|0.733|0.6136|0.6603|1.182|0.0|0.0|
|'3/correct_line'|72|0.7206|0.7266|0.6065|0.6555|1.181|0.0|0.0|
|'3/duration_digit'|110|0.7359|0.733|0.6136|0.6603|1.182|0.0|0.0|
|'3/incorrect_line'|38|0.7647|0.7519|0.633|0.7117|1.184|0.0|0.0|
|'5'|729|0.8952|0.9928|0.808|0.9618|1.979|0.075|0.085|
|'5/correct_line'|259|0.9678|0.9926|0.8906|0.967|1.985|0.0|0.0|
|'5/dose_digit'|505|0.9908|0.9978|0.9783|0.9916|2.133|0.0|0.0|
|'5/duration_digit'|224|0.6799|0.9089|0.0114|0.1056|1.634|0.246|0.277|
|'5/incorrect_line'|470|0.8553|0.9931|0.06|0.9592|1.977|0.117|0.132|
|'7'|219|0.412|0.3486|0.0065|0.0706|1.269|0.288|0.635|
|'7/correct_line'|38|0.8145|0.8818|0.5369|0.7459|1.684|0.0|0.026|
|'7/duration_digit'|219|0.412|0.3486|0.0065|0.0706|1.269|0.288|0.635|
|'7/incorrect_line'|181|0.3274|0.2942|0.0063|0.0161|1.182|0.348|0.762|
|'a'|1500|0.9857|0.9991|0.9715|0.9925|3.135|0.001|0.007|
|'a/correct_line'|458|0.9891|0.9994|0.9698|0.9915|3.17|0.0|0.004|
|'a/duration_neighbor'|232|0.9971|0.9989|0.9961|0.9977|3.168|0.0|0.0|
|'a/incorrect_line'|1042|0.9842|0.999|0.9723|0.9931|3.12|0.002|0.008|
|'a/other'|1268|0.9836|0.9993|0.9689|0.9861|3.129|0.002|0.008|
|'e'|1341|0.8777|0.9946|0.4111|0.9043|2.03|0.009|0.097|
|'e/correct_line'|492|0.8945|0.9954|0.5559|0.8854|2.077|0.0|0.071|
|'e/incorrect_line'|849|0.868|0.9942|0.3882|0.9187|2.002|0.014|0.112|
|'e/other'|1341|0.8777|0.9946|0.4111|0.9043|2.03|0.009|0.097|
|'o'|1191|0.8992|0.9988|0.4699|0.9948|2.425|0.0|0.087|
|'o/correct_line'|308|0.9456|0.9992|0.74|0.9972|2.591|0.0|0.019|
|'o/duration_neighbor'|232|0.9887|0.9989|0.9929|0.9972|1.884|0.0|0.0|
|'o/incorrect_line'|883|0.8831|0.9987|0.3914|0.9924|2.367|0.0|0.111|
|'o/other'|959|0.8776|0.9988|0.3951|0.9895|2.556|0.0|0.108|
|'r'|1001|0.8517|0.9946|0.4724|0.7023|2.147|0.023|0.132|
|'r/correct_line'|293|0.8554|0.9955|0.4777|0.6707|2.259|0.0|0.137|
|'r/duration_neighbor'|232|0.991|0.9994|0.9896|0.9971|1.845|0.0|0.004|
|'r/incorrect_line'|708|0.8501|0.9939|0.4624|0.7305|2.1|0.032|0.13|
|'r/other'|769|0.8097|0.9905|0.4412|0.6089|2.238|0.03|0.17|

All target occurrences and all characters are retained in character_statistics.json. Non-schedule/non-duration numerals are dose-context under this fixed prescription grammar, not a general clinical parser. Correct/incorrect-line strata refer to exact beam50 full-line equality, not token correctness.

## Greedy versus beam50 paths

|Split|Cohort N|Exact target in top5|Correct schedule appears in top5|Median target minus top1 logP|
|---|---|---|---|---|
|train|568|446|216|-0.472|
|validation|75|14|30|-5.365|

Exact target absent from top5 means absent only from the returned hypotheses, not from all explored beam states. Beam scores are pruned sequence log probabilities; the exact forward target score includes all valid target paths, while Viterbi is only the single best constrained path. These are not interchangeable. Class0 is filtered by the existing decoder; no padding-filter behavior was changed. Raw argmax paths, collapsed output and top5 scores are retained.

## Observational geometry correlations

|Group|N|Mean font size|Mean line length|Mean text width|Mean token x-start|Mean token x-end|
|---|---|---|---|---|---|---|
|duration/fitted:False/correct|239|22.99|35.03|382.28|291.2|345.49|
|duration/fitted:False/incorrect|191|22.92|33.96|368.04|290.6|372.1|
|duration/fitted:True/correct|110|19.61|46.8|479.72|315.5|395.94|
|duration/fitted:True/incorrect|13|19.54|44.85|475.08|338.08|413.92|
|duration/renderer:arial/correct|50|22.58|39.22|398.78|289.41|348.17|
|duration/renderer:arial/incorrect|29|23.0|34.59|366.14|295.34|374.3|
|duration/renderer:calibri/correct|41|22.98|39.15|370.8|266.05|320.46|
|duration/renderer:calibri/incorrect|28|23.07|33.43|319.86|253.29|328.39|
|duration/renderer:cambria/correct|42|23.0|37.33|374.4|274.16|327.54|
|duration/renderer:cambria/incorrect|36|22.97|34.75|345.94|269.99|354.52|
|duration/renderer:comic/correct|45|22.33|37.96|412.76|284.58|345.87|
|duration/renderer:comic/incorrect|22|22.91|34.95|389.95|304.09|398.36|
|duration/renderer:consola/correct|49|21.55|37.06|427.78|326.16|389.35|
|duration/renderer:consola/incorrect|17|22.76|33.65|421.82|353.82|430.76|
|duration/renderer:cour/correct|54|19.52|40.85|456.76|323.3|398.78|
|duration/renderer:cour/incorrect|13|22.31|32.62|425.15|327.08|433.69|
|duration/renderer:georgia/correct|35|22.74|39.43|404.54|288.94|349.86|
|duration/renderer:georgia/incorrect|32|22.75|35.44|364.12|281.56|354.38|
|duration/renderer:segoepr/correct|33|21.33|38.67|451.79|334.82|406.06|
|duration/renderer:segoepr/incorrect|27|21.59|36.3|426.48|316.89|391.67|
|duration/train/correct|316|21.99|38.75|408.94|295.1|356.72|
|duration/train/incorrect|177|22.88|34.4|366.99|290.08|372.19|
|duration/validation/correct|33|21.33|38.67|451.79|334.82|406.06|
|duration/validation/incorrect|27|21.59|36.3|426.48|316.89|391.67|
|schedule/fitted:False/correct|129|22.98|37.07|397.41|238.13|295.4|
|schedule/fitted:False/incorrect|104|22.89|30.91|335.01|241.32|297.88|
|schedule/fitted:True/correct|50|19.38|46.06|479.34|267.28|324.16|
|schedule/fitted:True/incorrect|15|18.07|48.0|474.67|268.6|318.6|
|schedule/renderer:arial/correct|24|22.79|41.5|418.96|258.16|310.74|
|schedule/renderer:arial/incorrect|23|22.74|33.09|338.65|213.81|266.73|
|schedule/renderer:calibri/correct|18|23.11|38.61|362.11|209.22|258.22|
|schedule/renderer:calibri/incorrect|14|22.57|33.29|306.64|227.57|276.07|
|schedule/renderer:cambria/correct|27|22.85|38.44|378.7|224.8|278.14|
|schedule/renderer:cambria/incorrect|11|23.0|31.55|313.18|220.36|273.54|
|schedule/renderer:comic/correct|15|22.27|42.2|445.93|251.33|305.53|
|schedule/renderer:comic/incorrect|9|23.11|29.56|326.11|234.89|288.78|
|schedule/renderer:consola/correct|22|21.55|37.77|438.27|259.68|318.77|
|schedule/renderer:consola/incorrect|12|22.83|29.0|364.33|288.42|351.33|
|schedule/renderer:cour/correct|26|20.12|39.77|458.12|265.04|324.08|
|schedule/renderer:cour/incorrect|19|19.53|39.68|435.84|278.11|335.74|
|schedule/renderer:georgia/correct|21|22.71|39.33|399.05|236.19|288.95|
|schedule/renderer:georgia/incorrect|22|22.68|32.23|319.95|226.09|275.64|
|schedule/renderer:segoepr/correct|26|20.96|39.69|454.35|258.35|331.12|
|schedule/renderer:segoepr/incorrect|9|23.11|31.56|423.0|307.33|388.0|
|schedule/train/correct|153|22.14|39.56|414.51|244.22|298.73|
|schedule/train/incorrect|110|22.22|33.19|346.85|239.64|293.33|
|schedule/validation/correct|26|20.96|39.69|454.35|258.35|331.12|
|schedule/validation/incorrect|9|23.11|31.56|423.0|307.33|388.0|

Renderer, phrase, length, font fitting and token location are confounded. Validation is Segoe Print only. These summaries cannot identify geometry or renderer as a causal mechanism. Prefix advances approximate glyph location; frame×4 is only a coordinate proxy, not registered receptive-field alignment. No image was regenerated.

## Augmentation implementation audit

Current light augmentation applies perspective then expanded-canvas rotation, optional Gaussian blur, resizing to64×512, then brightness. Noise/JPEG, explicit scale/shift/shear/elastic transforms are disabled. Perspective radius .012 at64×512 yields ceil(64×.012×8/9)=1: each integer corner range contains only the original corner, so this configured perspective is effectively identity (not a6-pixel horizontal displacement). Rotation radius1.5° is multiplied by8/9, giving at most1.3333°; its expanded height can reach75 before resizing to64, introducing **vertical scaling**, interpolation and centering shifts. Expanded width can reach513, giving slight horizontal scaling. Blur probability.12 yields one3×3 Gaussian pass; brightness probability.2, range.92–1.08 affects local contrast and clips high intensities.

Controlled seeded in-memory examples: 263 schedule-bearing training lines; paired approximate token masks edge-ink cases 0. Width ratio {'n': 263, 'mean': 1.0028734508248742, 'median': 1.0, 'p10': 1.0, 'p25': 1.0}; horizontal centroid shift {'n': 263, 'mean': -0.1398215339697809, 'median': -0.08909952606634874, 'p10': -0.8335496341664621, 'p25': -0.3804688971031709}. Full per-example bounds, ink counts, contrast proxy and Laplacian variance are retained. These are **not proven historical epoch replays**: current source/seed reproducibility does not prove the source/random state used during completed training. No glyph-completeness claim follows from zero edge ink; approximate masks may exclude kerning spill. Geometry effects are plausible exposure, not an established cause of the frozen errors.

## Clearest alignment examples

|ID|Split|Target token|Beam token|Greedy line|Beam line|Assigned emissions|
|---|---|---|---|---|---|---|
|validation_00004|validation|1-0-0|'1-0-0'|PCM  625 650 1-0-0 for 5 days aftr food|PCM  625 650 1-0-0 for 5 days after food|first_digit:1@44-45 p=0.9952 argmax=4; first_hyphen:-@46-49 p=0.9956 argmax=2; middle_digit:0@50-52 p=0.9827 argmax=3; second_hyphen:-@53-56 p=0.9922 argmax=2; final_digit:0@57-59 p=0.9971 argmax=3|
|validation_00044|validation|0-0-1|'0-0-1'|Metformin  65  Ocg  0-0-1  x 5d|Metformin  50  Ocg  0-0-1  x 5d|first_digit:0@73-75 p=0.9919 argmax=3; first_hyphen:-@76-80 p=0.9955 argmax=2; middle_digit:0@81-83 p=0.9823 argmax=3; second_hyphen:-@84-85 p=0.8240 argmax=2; final_digit:1@86-90 p=0.9950 argmax=4|
|validation_00019|validation|1-0-0|'1-0-0'|PCM 250 g 1-0 -0 x 5d|PCM 250 g 1-0-0 x 5d|first_digit:1@40-43 p=0.9830 argmax=4; first_hyphen:-@44-46 p=0.9948 argmax=2; middle_digit:0@47-50 p=0.9934 argmax=3; second_hyphen:-@51-54 p=0.9877 argmax=2; final_digit:0@55-56 p=0.9884 argmax=3|
|validation_00047|validation|1-0-0|' -1'|Tab Panetiazole  20 g  -1|Tab Panetirazole  20 g  -1|first_digit:1@115-115 p=0.1967 argmax=2; first_hyphen:-@116-124 p=0.9755 argmax=2; middle_digit:0@125-125 p=0.0380 argmax=2; second_hyphen:-@126-126 p=0.5620 argmax=2; final_digit:0@127-127 p=0.1549 argmax=4|
|train_00006|train|1-0-0|'0-1'|Amoxicillin 5 mcg -1|Amoxicillin 5 mcg 0-1|first_digit:1@114-114 p=0.2790 argmax=2; first_hyphen:-@115-124 p=0.9766 argmax=2; middle_digit:0@125-125 p=0.0345 argmax=2; second_hyphen:-@126-126 p=0.5425 argmax=2; final_digit:0@127-127 p=0.1394 argmax=4|
|train_00658|train|1-0-0|'0-1'|Pacetamol 5 mcg -1|Paracetamol 5 mcg 0-1|first_digit:1@114-114 p=0.2886 argmax=2; first_hyphen:-@115-124 p=0.9765 argmax=2; middle_digit:0@125-125 p=0.0348 argmax=2; second_hyphen:-@126-126 p=0.5295 argmax=2; final_digit:0@127-127 p=0.1417 argmax=4|
|train_00535|train|x 5d|'x 5d'|Cap Cetirizine 625 mcg 1-1 x 5d as need|Cap Cetirizine 625 mcg 1-1-1 x 5d as needed|numeral:5@85-87 p=0.9919 argmax=8|
|train_00184|train|x 5d|'x 5d'|Tablet Cetirizine 650 mg BD x 5d after fod|Tablet Cetirizine 650 mg BD x 5d after fod|numeral:5@76-76 p=0.9911 argmax=8|
|train_00546|train|x 5d|'x 5d'|Tab Pacetamol 250 mcg TDS x 5d at bedtime|Tab Paracetamol 250 mcg TDS x 5d at bedtime|numeral:5@84-85 p=0.9875 argmax=8|
|train_00470|train|for 7 days|'for days'|Cetirizine 650 g SOS for days|Cetirizine 650 g SOS for days|numeral:7@109-109 p=0.0051 argmax=1|
|train_00302|train|for 7 days|'for days'|Cetirizine 650 ml AC for days|Cetirizine 650 ml AC for days|numeral:7@75-75 p=0.0053 argmax=1|
|train_00421|train|for 7 days|'for days'|Inj PCM 10 ml SOS for days|Inj PCM 10 ml SOS for days|numeral:7@67-67 p=0.0054 argmax=1|

## Evidence classification and smallest next experiment

See [FINDINGS.md](FINDINGS.md) for the evidence-based interpretation of these measurements. Categories A–G are descriptive possibilities, not established causes of the training regression. No experiment is launched by this report.

## Freeze, optional test confirmation and artifacts

Hypotheses, .1/.5 descriptive emission cutoffs, forced-alignment/projection rules, ±3-frame window and source/configuration hashes are recorded in audit_config.json and analysis_freeze.json. **Test confirmation was not run**; test_confirmation.json records that choice. No test predictions were inspected in this audit.

Created source files: app/ctc_alignment_audit.py, scripts/audit_ctc_schedules.py, scripts/report_ctc_schedules.py, tests/test_ctc_alignment_audit.py. New artifacts are confined to this versioned benchmark directory; no previous report is overwritten. Raw arrays cover all800 train/validation lines; full per-frame JSON traces and forced paths cover the diagnostic cohort. Final tests/checks and Git status: [CHECKS.md](CHECKS.md).
