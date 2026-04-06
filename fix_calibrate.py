content = open('calibrate.py', encoding='utf-8').read()
fixed = content.replace('"raw_prob"', '"raw_prob_model"').replace("'raw_prob'", "'raw_prob_model'")
open('calibrate.py', 'w', encoding='utf-8').write(fixed)
print('done')