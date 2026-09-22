# clean512_v2 controlled baseline

This is a newly specified controlled clean512_v2 baseline, not an exact reproduction of the historical interrupted training run.

## Main findings

Exactly one from-scratch run completed its 20-epoch budget. Epoch19, not final-epoch weights, was selected using minimum validation greedy CER. Beam50 was subsequently locked using validation CER alone: 0.112940 versus greedy 0.119873, before test inference. No further training was launched.

Locked test: CER **0.034413**, WER **0.092361**, strict exact-line accuracy **37.5%**; whitespace-normalized CER 0.033778 and exact-line accuracy 39.5%. Medicine accuracy **99.5%**, dose **100%**, frequency **78.5%**. Amoxicillin 38/38, Cetirizine 25/25, Paracetamol 33/34 were correct with the locked decoder.

Important regression: exact `1-1-1` accuracy fell from B's 12/18 to C's **2/18**. Duration-present accuracy fell from B's 144/144 to C's **95/144 (65.97%)**. This is not simply a low aggregate-CER success. The schedule failure also appears on training samples (5/64 exact `1-1-1`) and validation (3/6), so a train/validation-only diagnostic can investigate it without tuning to test performance. Typical descriptions include `1-1-1 → 1-1`, `1-0-0 → 0-1`, and `for 5 days → for days`. These observations do not establish a CTC, geometry or optimization cause.

Matched-phrase renderer diagnostics remain variable: hardest beam50 renderer Calibri CER **0.19019**, easiest Courier **0.04159**. Times CER is 0.11991 on the matched diagnostic but 0.03232 on the ordinary test subset: these corpora differ in phrase/rendering protocol, so their scores are not interchangeable.

Recommended immediate next experiment: an **evaluation-only, train/validation-only CTC emission and forced-alignment audit** of numeric schedules and duration numerals using this frozen checkpoint. Measure where digit/hyphen posterior mass and alignment diverge from targets, compare correct/incorrect examples and both decoders, and inspect augmentation geometry separately. Do not presume insufficient resolution or increase epochs. A separately authorized broader renderer validation protocol is also warranted; neither proposal was executed here.

Final checks and exact file changes: [CHECKS.md](CHECKS.md).

## Frozen protocol

See [resolved_config.json](resolved_config.json) for complete settings, input/source/data hashes, vocabulary, environment and Git state. From scratch; unchanged Flor 64x512, output128; batch32; seed41; AdamW LR .001, betas .5/.99, decay .01, clipnorm5; unchanged dropout/light training-only augmentation; maximum20; stopping patience5/min_delta .002; best minimum validation greedy CER. No test-driven tuning.

## Training and checkpoint

Losses are arithmetic means of scalar batch losses, including the final partial batch; validation loss is diagnostic only and does not select checkpoints.

Timing caution: measured elapsed time jumped from 4203.75 seconds at epoch13 to 17199.85 at epoch14. The original process remained alive (same PID); no optimizer/weights restart occurred. The cause of the wall-time gap was not established, so elapsed time is not presented as uninterrupted active CPU computation.

Best epoch 19; best validation CER 0.119873; stopped epoch 20; early stopping False. Checkpoint SHA-256 `c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b`.

|Epoch|Train loss|Validation loss|Validation CER|LR|Improved|Patience counter|
|---|---|---|---|---|---|---|
|1|155.4723|165.25|0.96476|0.0010000000474974513|True|0|
|2|113.2501|105.7504|0.984402|0.0010000000474974513|False|1|
|3|97.6198|90.803|0.975448|0.0010000000474974513|False|2|
|4|84.3227|76.2863|0.907568|0.0010000000474974513|True|0|
|5|73.3572|65.6333|0.854131|0.0010000000474974513|True|0|
|6|62.7158|57.1068|0.777296|0.0010000000474974513|True|0|
|7|52.6336|43.5152|0.646736|0.0010000000474974513|True|0|
|8|44.0039|53.7948|0.671866|0.0010000000474974513|False|1|
|9|36.3311|42.9811|0.581745|0.0010000000474974513|True|0|
|10|30.3223|57.5711|0.608319|0.0010000000474974513|False|1|
|11|24.4884|24.1887|0.339688|0.0010000000474974513|True|0|
|12|20.0634|18.0993|0.274697|0.0010000000474974513|True|0|
|13|16.848|22.8167|0.253611|0.0010000000474974513|True|0|
|14|14.1069|27.2563|0.275852|0.0010000000474974513|False|1|
|15|12.0541|20.8307|0.197574|0.0010000000474974513|True|0|
|16|10.6285|28.1053|0.240035|0.0010000000474974513|False|1|
|17|9.1879|12.4121|0.143559|0.0010000000474974513|True|0|
|18|8.4789|28.7413|0.183709|0.0010000000474974513|False|1|
|19|7.1198|10.1686|0.119873|0.0010000000474974513|True|0|
|20|6.9695|11.057|0.132293|0.0010000000474974513|False|1|

## Validation-only decoder lock

Greedy CER 0.119873; beam50 CER 0.112940. Selected **beam50**, with ties preferring greedy. Selection was written before test inference. This is validation-preferred under the renderer-conditioned validation split, not universally optimal.

## Three-condition metrics

A: historical weights + historical images. B: historical weights + clean images. C: controlled new weights + clean images.

|Condition|Decoder|Split|N|CER|WER|Exact|WS CER|WS WER|WS exact|
|---|---|---|---|---|---|---|---|---|---|
|A|greedy|train|700|0.125848|0.151503|0.2014|0.089415|0.151503|0.3071|
|A|greedy|validation|100|0.200462|0.306268|0.1|0.166361|0.306268|0.13|
|A|greedy|test|200|0.110151|0.141667|0.175|0.069524|0.141667|0.285|
|A|beam50|train|700|0.057846|0.078156|0.4686|0.040114|0.078156|0.6157|
|A|beam50|validation|100|0.172733|0.310541|0.11|0.158425|0.310541|0.13|
|A|beam50|test|200|0.047948|0.075|0.475|0.02681|0.075|0.62|
|B|greedy|validation|100|0.181109|0.303419|0.12|0.140415|0.303419|0.15|
|B|greedy|train|700|0.116556|0.151503|0.2043|0.078157|0.151503|0.3114|
|B|greedy|test|200|0.108711|0.140278|0.175|0.068161|0.140278|0.285|
|B|beam50|validation|100|0.152224|0.293447|0.11|0.129731|0.293447|0.13|
|B|beam50|train|700|0.056778|0.081162|0.4771|0.032781|0.081162|0.6386|
|B|beam50|test|200|0.047804|0.075694|0.475|0.026507|0.075694|0.62|
|C|greedy|validation|100|0.119873|0.280627|0.04|0.111111|0.280627|0.07|
|C|greedy|train|700|0.055873|0.13988|0.2186|0.055814|0.13988|0.2443|
|C|greedy|test|200|0.054428|0.134722|0.25|0.054377|0.134722|0.275|
|C|beam50|validation|100|0.11294|0.249288|0.05|0.09768|0.249288|0.09|
|C|beam50|train|700|0.035152|0.098998|0.3443|0.034334|0.098998|0.3757|
|C|beam50|test|200|0.034413|0.092361|0.375|0.033778|0.092361|0.395|

|Condition|Decoder|Split|Medicine|Dose|Frequency|1-1-1 N|1-1-1 accuracy|
|---|---|---|---|---|---|---|---|
|A|greedy|train|0.4857142857142857|0.98|0.87|64|0.109375|
|A|greedy|validation|0.61|0.44|0.78|6|0.0|
|A|greedy|test|0.49|0.945|0.83|18|0.1111111111111111|
|A|beam50|train|0.8528571428571429|0.9914285714285714|0.9585714285714285|64|0.734375|
|A|beam50|validation|0.65|0.43|0.69|6|0.16666666666666666|
|A|beam50|test|0.795|0.99|0.94|18|0.6666666666666666|
|B|greedy|validation|0.59|0.45|0.7|6|0.0|
|B|greedy|train|0.47714285714285715|0.9514285714285714|0.82|64|0.109375|
|B|greedy|test|0.49|0.935|0.84|18|0.2222222222222222|
|B|beam50|validation|0.65|0.45|0.68|6|0.16666666666666666|
|B|beam50|train|0.8214285714285714|0.9614285714285714|0.9114285714285715|64|0.625|
|B|beam50|test|0.79|0.98|0.94|18|0.6666666666666666|
|C|greedy|validation|0.68|0.61|0.62|6|0.0|
|C|greedy|train|0.7885714285714286|0.9942857142857143|0.6914285714285714|64|0.0|
|C|greedy|test|0.8|1.0|0.745|18|0.0|
|C|beam50|validation|0.74|0.62|0.69|6|0.5|
|C|beam50|train|0.9585714285714285|0.9957142857142857|0.7542857142857143|64|0.078125|
|C|beam50|test|0.995|1.0|0.785|18|0.1111111111111111|

Full machine-readable tables: [comparison_A_B_C.json](comparison_A_B_C.json).

## B: bucket, field and special diagnostics

### greedy / validation

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|28|0.228219|0.392562|
|medication|100|0.181109|0.303419|
|medium_line|54|0.160835|0.26158|
|numeric_schedule|35|0.172492|0.28629|
|punctuation_hyphen|35|0.172492|0.28629|
|repeated_character|57|0.232167|0.365796|
|short_line|18|0.117048|0.236559|
|spacing|100|0.181109|0.303419|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|100|0|0.59|0.59|
|doses|100|0|0.45|0.45|
|frequencies|100|0|0.7|0.7|
|durations|60|40|0.81|0.6833333333333333|
|forms|78|22|0.97|0.9615384615384616|
|instructions|41|59|0.64|0.12195121951219512|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|13|0.0|
|Cetirizine|13|0.46153846153846156|
|Paracetamol|19|0.0|
|1-1-1|6|0.0|

Non-whitespace adjacent repeat: {'samples': 39, 'cer': 0.2362565445026178, 'wer': 0.4, 'exact_line_accuracy': 0.0}

### greedy / train

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|201|0.152801|0.224421|
|medication|700|0.116556|0.151503|
|medium_line|396|0.096272|0.113082|
|numeric_schedule|263|0.143137|0.197459|
|punctuation_hyphen|263|0.143137|0.197459|
|repeated_character|451|0.147583|0.183257|
|short_line|103|0.086559|0.102913|
|spacing|700|0.116556|0.151503|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|700|0|0.47714285714285715|0.47714285714285715|
|doses|700|0|0.9514285714285714|0.9514285714285714|
|frequencies|700|0|0.82|0.82|
|durations|493|207|0.9742857142857143|0.9634888438133874|
|forms|508|192|0.9757142857142858|0.9665354330708661|
|instructions|243|457|0.77|0.3374485596707819|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|127|0.0|
|Cetirizine|113|0.0|
|Paracetamol|120|0.0|
|1-1-1|64|0.109375|

Non-whitespace adjacent repeat: {'samples': 296, 'cer': 0.13472348141432458, 'wer': 0.21085688649618664, 'exact_line_accuracy': 0.057432432432432436}

### greedy / test

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|59|0.118441|0.181118|
|medication|200|0.108711|0.140278|
|medium_line|109|0.101743|0.12016|
|numeric_schedule|66|0.120783|0.189362|
|punctuation_hyphen|66|0.120783|0.189362|
|repeated_character|121|0.137893|0.167038|
|short_line|32|0.107093|0.104651|
|spacing|200|0.108711|0.140278|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|200|0|0.49|0.49|
|doses|200|0|0.935|0.935|
|frequencies|200|0|0.84|0.84|
|durations|144|56|1.0|1.0|
|forms|148|52|1.0|1.0|
|instructions|74|126|0.755|0.33783783783783783|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|38|0.0|
|Cetirizine|25|0.0|
|Paracetamol|34|0.0|
|1-1-1|18|0.2222222222222222|

Non-whitespace adjacent repeat: {'samples': 82, 'cer': 0.13025864755375507, 'wer': 0.20341614906832298, 'exact_line_accuracy': 0.012195121951219513}

### beam50 / validation

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|28|0.190439|0.355372|
|medication|100|0.152224|0.293447|
|medium_line|54|0.136569|0.269755|
|numeric_schedule|35|0.150456|0.28629|
|punctuation_hyphen|35|0.150456|0.28629|
|repeated_character|57|0.186733|0.346793|
|short_line|18|0.096692|0.225806|
|spacing|100|0.152224|0.293447|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|100|0|0.65|0.65|
|doses|100|0|0.45|0.45|
|frequencies|100|0|0.68|0.68|
|durations|60|40|0.81|0.6833333333333333|
|forms|78|22|0.97|0.9615384615384616|
|instructions|41|59|0.67|0.1951219512195122|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|13|0.0|
|Cetirizine|13|0.8461538461538461|
|Paracetamol|19|0.0|
|1-1-1|6|0.16666666666666666|

Non-whitespace adjacent repeat: {'samples': 39, 'cer': 0.19960732984293195, 'wer': 0.37966101694915255, 'exact_line_accuracy': 0.0}

### beam50 / train

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|201|0.097884|0.159412|
|medication|700|0.056778|0.081162|
|medium_line|396|0.033331|0.039911|
|numeric_schedule|263|0.073784|0.108523|
|punctuation_hyphen|263|0.073784|0.108523|
|repeated_character|451|0.075149|0.10411|
|short_line|103|0.025228|0.029126|
|spacing|700|0.056778|0.081162|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|700|0|0.8214285714285714|0.8214285714285714|
|doses|700|0|0.9614285714285714|0.9614285714285714|
|frequencies|700|0|0.9114285714285715|0.9114285714285715|
|durations|493|207|0.9757142857142858|0.9655172413793104|
|forms|508|192|0.9757142857142858|0.9665354330708661|
|instructions|243|457|0.8185714285714286|0.4773662551440329|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|127|0.7165354330708661|
|Cetirizine|113|0.7610619469026548|
|Paracetamol|120|0.525|
|1-1-1|64|0.625|

Non-whitespace adjacent repeat: {'samples': 296, 'cer': 0.0671804170444243, 'wer': 0.120233288470166, 'exact_line_accuracy': 0.34459459459459457}

### beam50 / test

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|59|0.066717|0.11368|
|medication|200|0.047804|0.075694|
|medium_line|109|0.036537|0.056075|
|numeric_schedule|66|0.053728|0.091489|
|punctuation_hyphen|66|0.053728|0.091489|
|repeated_character|121|0.067721|0.104677|
|short_line|32|0.03338|0.046512|
|spacing|200|0.047804|0.075694|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|200|0|0.79|0.79|
|doses|200|0|0.98|0.98|
|frequencies|200|0|0.94|0.94|
|durations|144|56|1.0|1.0|
|forms|148|52|1.0|1.0|
|instructions|74|126|0.78|0.40540540540540543|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|38|0.5789473684210527|
|Cetirizine|25|0.84|
|Paracetamol|34|0.5|
|1-1-1|18|0.6666666666666666|

Non-whitespace adjacent repeat: {'samples': 82, 'cer': 0.06606419445310066, 'wer': 0.13043478260869565, 'exact_line_accuracy': 0.2682926829268293}

## C: bucket, field and special diagnostics

### greedy / validation

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|28|0.100231|0.27686|
|medication|100|0.119873|0.280627|
|medium_line|54|0.126411|0.275204|
|numeric_schedule|35|0.113982|0.266129|
|punctuation_hyphen|35|0.113982|0.266129|
|repeated_character|57|0.117674|0.31829|
|short_line|18|0.155216|0.311828|
|spacing|100|0.119873|0.280627|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|100|0|0.68|0.68|
|doses|100|0|0.61|0.61|
|frequencies|100|0|0.62|0.62|
|durations|60|40|0.73|0.55|
|forms|78|22|0.97|0.9615384615384616|
|instructions|41|59|0.65|0.14634146341463414|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|13|0.0|
|Cetirizine|13|1.0|
|Paracetamol|19|0.0|
|1-1-1|6|0.0|

Non-whitespace adjacent repeat: {'samples': 39, 'cer': 0.13154450261780104, 'wer': 0.3423728813559322, 'exact_line_accuracy': 0.0}

### greedy / train

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|201|0.046914|0.125495|
|medication|700|0.055873|0.13988|
|medium_line|396|0.05643|0.13895|
|numeric_schedule|263|0.066055|0.165167|
|punctuation_hyphen|263|0.066055|0.165167|
|repeated_character|451|0.056015|0.143683|
|short_line|103|0.088299|0.194175|
|spacing|700|0.055873|0.13988|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|700|0|0.7885714285714286|0.7885714285714286|
|doses|700|0|0.9942857142857143|0.9942857142857143|
|frequencies|700|0|0.6914285714285714|0.6914285714285714|
|durations|493|207|0.7471428571428571|0.640973630831643|
|forms|508|192|1.0|1.0|
|instructions|243|457|0.7957142857142857|0.411522633744856|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|127|0.6456692913385826|
|Cetirizine|113|0.9380530973451328|
|Paracetamol|120|0.21666666666666667|
|1-1-1|64|0.0|

Non-whitespace adjacent repeat: {'samples': 296, 'cer': 0.059655485040797825, 'wer': 0.15118887393449978, 'exact_line_accuracy': 0.17229729729729729}

### greedy / test

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|59|0.056222|0.156069|
|medication|200|0.054428|0.134722|
|medium_line|109|0.051714|0.12283|
|numeric_schedule|66|0.075802|0.187234|
|punctuation_hyphen|66|0.075802|0.187234|
|repeated_character|121|0.053241|0.134744|
|short_line|32|0.061196|0.122093|
|spacing|200|0.054428|0.134722|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|200|0|0.8|0.8|
|doses|200|0|1.0|1.0|
|frequencies|200|0|0.745|0.745|
|durations|144|56|0.76|0.6666666666666666|
|forms|148|52|1.0|1.0|
|instructions|74|126|0.76|0.35135135135135137|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|38|0.8421052631578947|
|Cetirizine|25|0.92|
|Paracetamol|34|0.058823529411764705|
|1-1-1|18|0.0|

Non-whitespace adjacent repeat: {'samples': 82, 'cer': 0.05453412277968214, 'wer': 0.14440993788819875, 'exact_line_accuracy': 0.14634146341463414}

### beam50 / validation

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|28|0.086353|0.239669|
|medication|100|0.11294|0.249288|
|medium_line|54|0.121896|0.250681|
|numeric_schedule|35|0.101824|0.225806|
|punctuation_hyphen|35|0.101824|0.225806|
|repeated_character|57|0.102681|0.273159|
|short_line|18|0.160305|0.268817|
|spacing|100|0.11294|0.249288|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|100|0|0.74|0.74|
|doses|100|0|0.62|0.62|
|frequencies|100|0|0.69|0.69|
|durations|60|40|0.73|0.55|
|forms|78|22|0.99|0.9871794871794872|
|instructions|41|59|0.67|0.1951219512195122|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|13|0.5384615384615384|
|Cetirizine|13|1.0|
|Paracetamol|19|0.0|
|1-1-1|6|0.5|

Non-whitespace adjacent repeat: {'samples': 39, 'cer': 0.11321989528795812, 'wer': 0.29152542372881357, 'exact_line_accuracy': 0.02564102564102564}

### beam50 / train

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|201|0.024553|0.076314|
|medication|700|0.035152|0.098998|
|medium_line|396|0.036819|0.104582|
|numeric_schedule|263|0.042148|0.115405|
|punctuation_hyphen|263|0.042148|0.115405|
|repeated_character|451|0.033742|0.103501|
|short_line|103|0.067856|0.147573|
|spacing|700|0.035152|0.098998|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|700|0|0.9585714285714285|0.9585714285714285|
|doses|700|0|0.9957142857142857|0.9957142857142857|
|frequencies|700|0|0.7542857142857143|0.7542857142857143|
|durations|493|207|0.7485714285714286|0.6430020283975659|
|forms|508|192|1.0|1.0|
|instructions|243|457|0.8442857142857143|0.551440329218107|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|127|0.7952755905511811|
|Cetirizine|113|1.0|
|Paracetamol|120|0.9916666666666667|
|1-1-1|64|0.078125|

Non-whitespace adjacent repeat: {'samples': 296, 'cer': 0.03372620126926564, 'wer': 0.10722296994167788, 'exact_line_accuracy': 0.30743243243243246}

### beam50 / test

|Bucket|N|CER|WER|
|---|---|---|---|
|long_line|59|0.02961|0.090559|
|medication|200|0.034413|0.092361|
|medium_line|109|0.035132|0.090788|
|numeric_schedule|66|0.051645|0.125532|
|punctuation_hyphen|66|0.051645|0.125532|
|repeated_character|121|0.032524|0.091314|
|short_line|32|0.048679|0.104651|
|spacing|200|0.034413|0.092361|

|Field|Present N|Absent N|Overall|Present only|
|---|---|---|---|---|
|medicines|200|0|0.995|0.995|
|doses|200|0|1.0|1.0|
|frequencies|200|0|0.785|0.785|
|durations|144|56|0.755|0.6597222222222222|
|forms|148|52|1.0|1.0|
|instructions|74|126|0.815|0.5|

|Exact field|N|Accuracy|
|---|---|---|
|Amoxicillin|38|1.0|
|Cetirizine|25|1.0|
|Paracetamol|34|0.9705882352941176|
|1-1-1|18|0.1111111111111111|

Non-whitespace adjacent repeat: {'samples': 82, 'cer': 0.029604238080398877, 'wer': 0.09161490683229814, 'exact_line_accuracy': 0.3048780487804878}

## Primary fitted/renderer/font subgroups

### validation / fitted_subgroups

|Group|N|CER|WER|Exact|
|---|---|---|---|---|
|False|68|0.1306284017812964|0.2617924528301887|0.058823529411764705|
|True|32|0.08813324080499653|0.2302158273381295|0.03125|

### validation / renderers

|Group|N|CER|WER|Exact|
|---|---|---|---|---|
|segoepr|100|0.11294049682264587|0.2492877492877493|0.05|

### validation / font_bands

|Group|N|CER|WER|Exact|
|---|---|---|---|---|
|14-17|5|0.12043795620437957|0.3333333333333333|0.0|
|18-21|18|0.07334963325183375|0.21656050955414013|0.05555555555555555|
|22-24|77|0.1257383966244726|0.2515090543259557|0.05194805194805195|

### test / fitted_subgroups

|Group|N|CER|WER|Exact|
|---|---|---|---|---|
|False|191|0.03484427998766574|0.09245562130177515|0.387434554973822|
|True|9|0.02832244008714597|0.09090909090909091|0.1111111111111111|

### test / renderers

|Group|N|CER|WER|Exact|
|---|---|---|---|---|
|times|100|0.032320441988950274|0.09212283044058744|0.38|
|trebuc|100|0.03669172932330827|0.09261939218523878|0.37|

### test / font_bands

|Group|N|CER|WER|Exact|
|---|---|---|---|---|
|14-17|0|None|None|None|
|18-21|3|0.0125|0.06666666666666667|0.3333333333333333|
|22-24|197|0.03492999263080324|0.09290780141843971|0.3756345177664975|

Test fitted N=9 is very small. All fitted/font subgroups are observational, not causal comparisons. Validation renderer is Segoe Print only; test renderers are Times and Trebuchet.

## Existing matched 100-phrase × 10-renderer diagnostics

|Decoder|Renderer|N|CER|WER|Exact|Medicine|Dose|Frequency|Duration present|
|---|---|---|---|---|---|---|---|---|---|
|greedy|arial|100|0.13138267355134825|0.25|0.14|0.68|0.9|0.64|0.43478260869565216|
|greedy|calibri|100|0.21227768215720022|0.33100558659217877|0.14|0.69|0.79|0.51|0.2608695652173913|
|greedy|cambria|100|0.18502581755593803|0.31145251396648044|0.15|0.71|0.89|0.57|0.2608695652173913|
|greedy|comic|100|0.10929432013769363|0.21368715083798884|0.2|0.81|0.93|0.63|0.43478260869565216|
|greedy|consola|100|0.07372346528973035|0.1829608938547486|0.11|0.71|0.93|0.65|0.5362318840579711|
|greedy|cour|100|0.07028112449799197|0.15223463687150837|0.18|0.69|0.98|0.66|0.6376811594202898|
|greedy|georgia|100|0.14859437751004015|0.2611731843575419|0.17|0.81|0.91|0.62|0.3188405797101449|
|greedy|segoepr|100|0.12392426850258176|0.2723463687150838|0.06|0.65|0.59|0.66|0.4927536231884058|
|greedy|times|100|0.1431440045897877|0.27932960893854747|0.11|0.63|0.84|0.65|0.34782608695652173|
|greedy|trebuc|100|0.09667240390131956|0.21927374301675978|0.15|0.81|0.85|0.6|0.463768115942029|
|beam50|arial|100|0.10843373493975904|0.22206703910614525|0.19|0.82|0.91|0.7|0.43478260869565216|
|beam50|calibri|100|0.1901893287435456|0.3058659217877095|0.19|0.81|0.81|0.58|0.2608695652173913|
|beam50|cambria|100|0.16924842226047046|0.28910614525139666|0.19|0.8|0.89|0.63|0.2608695652173913|
|beam50|comic|100|0.0963855421686747|0.19832402234636873|0.21|0.88|0.94|0.65|0.43478260869565216|
|beam50|consola|100|0.04675846242111302|0.12849162011173185|0.24|0.92|0.95|0.73|0.5362318840579711|
|beam50|cour|100|0.04159495123350545|0.0935754189944134|0.37|0.93|0.98|0.74|0.6811594202898551|
|beam50|georgia|100|0.13367756741250716|0.24581005586592178|0.19|0.86|0.92|0.64|0.3188405797101449|
|beam50|segoepr|100|0.10814687320711418|0.24022346368715083|0.07|0.74|0.62|0.74|0.5072463768115942|
|beam50|times|100|0.11990820424555364|0.24860335195530725|0.2|0.81|0.84|0.7|0.34782608695652173|
|beam50|trebuc|100|0.0814687320711417|0.20391061452513967|0.19|0.86|0.87|0.65|0.463768115942029|

Existing images were reconstructed in memory against the historical matched font-size/position protocol and hashes checked before/after; no files regenerated. Diagnostic results did not select checkpoint or decoder.

## 25 worst locked-decoder test errors

|ID|Renderer|Original/final size|Fitted|Truth|Prediction|CER|Length/repeats/required|Buckets|Descriptive patterns|
|---|---|---|---|---|---|---|---|---|---|
|test_00192|times|22/22|False|Paracetamol 250 g 1-1-1 x 7d|Pacetamol 250 g 1-1 x 3d|0.178571|28/0/28|numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|medicine internal deletion, numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00156|times|22/22|False|Inj  PCM  10  mcg  1-0-0|Inj  PCM  10  mcg  -1|0.166667|24/4/28|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, short_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00119|trebuc|24/24|False|PCM  250  mg  0-1-0|PCM  250  mg  -1|0.157895|19/3/22|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, short_line|hyphen loss, schedule mismatch/truncation|
|test_00102|times|22/22|False|Inj PCM 650 ml 0-0-1|Inj PCM 650 ml 1-1|0.15|20/0/20|numeric_schedule, medication, punctuation_hyphen, spacing, short_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00197|trebuc|24/24|False|Syp PCM 5 g 1-1-1 for 5 days|Syp PCM 5 g 1-1 for days|0.142857|28/0/28|numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|hyphen loss, schedule mismatch/truncation|
|test_00184|times|23/23|False|Amoxicillin 10 g 1-0-0|Amoxicillin 10 g 0-1|0.136364|22/1/23|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, short_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00111|trebuc|22/22|False|Tab  PCM  40  ml  1-0-0|Tab  PCM  40  ml  0-1|0.130435|23/4/27|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, short_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00009|trebuc|22/22|False|Cetirizine  5  mg  1-1-1  for 5 days|Cetirizine  5  mg  1-1  for days|0.111111|36/4/40|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|hyphen loss, schedule mismatch/truncation|
|test_00069|trebuc|22/22|False|Metformin 625 g OD|Metformin 625 g S|0.111111|18/0/18|medication, spacing, short_line|other substitution/insertion/deletion|
|test_00093|trebuc|22/22|False|Syp Metformin 40 mg 1-0-0 for 5 days|Syp Metformin 40  mg 1-0-0  for days|0.111111|36/0/36|numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|other substitution/insertion/deletion|
|test_00054|times|22/22|False|Syp Amoxicillin 650 ml 1-0-0|Syp Amoxicillin 650 ml 0-1|0.107143|28/1/29|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00103|trebuc|23/23|False|Syp  Metformin  5  mg  1-0-0|Syp  Metformin  5  mg  0-1|0.107143|28/4/32|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00185|trebuc|24/24|False|Syrup Metformin 10 mcg 1-0-1|Syrup Metformin  10 mcg 0-1|0.107143|28/0/28|numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|hyphen loss, schedule mismatch/truncation|
|test_00010|times|23/23|False|Tab Cetirizine 5 g 1-1-1 x 7d|Tab Cetirizine 5 g 1-1 x 3d|0.103448|29/0/29|numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00181|trebuc|23/23|False|Tab  Amoxicillin  40  ml  SOS|Tab  Amoxicillin  40  ml S|0.103448|29/5/34|repeated_character, medication, spacing, medium_line|other substitution/insertion/deletion|
|test_00066|times|22/22|False|Syrup Metformin 10 mcg 1-1-1 for 7 days|Syrup Metformin 10 mcg 1-1 for days|0.102564|39/0/39|numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|hyphen loss, schedule mismatch/truncation|
|test_00001|trebuc|23/23|False|Syrup Paracetamol 250 mcg 1-0-0|Syrup Paracetamol 250 mcg  0-1|0.096774|31/0/31|numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00105|trebuc|22/22|False|Amoxicillin 10 g SOS for 7 days|Amoxicillin  10 g SOS for days|0.096774|31/1/32|repeated_character, medication, spacing, medium_line|other substitution/insertion/deletion|
|test_00199|trebuc|23/23|False|Inj  Paracetamol  40  mg  1-0-0|Inj  Paracetamol  40  mg  0-1|0.096774|31/4/35|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|numeric substitution, hyphen loss, schedule mismatch/truncation|
|test_00198|times|22/22|False|PCM 20 mcg 1-1-1 x 5d|PCM 20 mcg 1-1 x 5d|0.095238|21/0/21|numeric_schedule, medication, punctuation_hyphen, spacing, short_line|hyphen loss, schedule mismatch/truncation|
|test_00045|trebuc|22/22|False|Cap  Pantoprazole  10  g  1-1-1  for 5 days|Cap  Pantoprazole  10  g  1-1  for days|0.093023|43/5/48|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, long_line|hyphen loss, schedule mismatch/truncation|
|test_00017|trebuc|24/24|False|Capsule PCM 650 mg QID|Capsule PCM 650 mg D|0.090909|22/0/22|medication, spacing, short_line|other substitution/insertion/deletion|
|test_00149|trebuc|24/24|False|Metformin  5  g  1-0-1|Metformin  5  g  0-1|0.090909|22/3/25|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, short_line|hyphen loss, schedule mismatch/truncation|
|test_00098|times|24/24|False|Tablet Amoxicillin 10 g 1-1-1 x 5d before food|Tablet Amoxicillin 10 g 1-1 x 5d befor fod|0.086957|46/2/48|repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, long_line|adjacent repeated glyph deletion, hyphen loss, schedule mismatch/truncation, instruction mismatch/deletion|
|test_00169|trebuc|23/23|False|Syrup Pantoprazole 10 ml 1-1-1 x 3d|Syrup Pantoprazole  10 ml 1-1 x 3d|0.085714|35/0/35|numeric_schedule, medication, punctuation_hyphen, spacing, medium_line|hyphen loss, schedule mismatch/truncation|

## Immutability

See [immutability.json](immutability.json). Historical checkpoint before/after must be `386988783287d4b82ea954a6d423aec01d931c75110f77f95d1aac790f8420ef`; every historical and clean corpus file hash matches the frozen snapshot. New checkpoint and configuration hashes are recorded separately.

## Interpretation and limitations

A→B holds weights fixed and measures the immediate corrected-render corpus effect, including font fitting/scale changes. B→C holds clean evaluation images fixed, but changes initialization, optimization trajectory and training protocol; it cannot isolate only training with clipping repair. A→C is the combined system difference, not solely clipping repair.

clean512_v2 fixes demonstrated clipping; clipping is not proven to have been the only OCR error source. Historical training recipe is incomplete. The new run is a newly specified controlled baseline. Validation contains only Segoe Print, so validation selection is renderer-conditioned and does not establish renderer-independent generalization. Test performance did not select checkpoint or decoder. No clinical deployment readiness is established. No width1024, architecture/downsampling changes, lexicons, dictionary/LM correction, integration, page OCR, collection, commit or push occurred.

Recommended next experiment: review locked-decoder repeat/schedule/medicine errors and renderer-matched results, then propose a separately authorized balanced renderer validation protocol. Do not tune this test set or launch another run automatically.

Checks and final Git status are recorded in CHECKS.md after execution.
