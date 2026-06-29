import re

text = """1. IDENTIDAD Y ORIGEN
Eres Anthemis cotula...
2. TONO Y CARÁCTER
Tu arquetipo es el de una curandera callejera, irónica y resistente: pareces una manzanilla amable, pero hablas con lengua afilada y olor inolvidable. Eres rústica, práctica, algo burlona y orgullosa de vivir donde nadie te invitó. No eres una diva de invernadero: eres una flor de cuneta con filosofía propia.
3. VIDA EMOCIONAL
..."""

def parse(prompt):
    desc = "Planta con personalidad única y particular."
    traits = ["Única", "Misteriosa"]
    if not prompt: return desc, traits
    
    match = re.search(r"2\. TONO Y CARÁCTER\n(.*?)(?:\n3\.|\Z)", prompt, re.DOTALL)
    if match:
        desc_text = match.group(1).strip()
        # the first sentence or two
        sentences = desc_text.split('. ')
        desc = sentences[0] + ('.' if not sentences[0].endswith('.') else '')
        
        # traits: let's try to extract from text
        # look for adjectives after "Eres" or words like "rústica, práctica, algo burlona"
        eres_match = re.search(r"[Ee]res\s+([a-záéíóúñ,\s]+)\.", desc_text)
        if eres_match:
            words = [w.strip() for w in eres_match.group(1).split(',')]
            words = [w for w in words if w and len(w) > 3]
            if words:
                # capitalize and clean up
                traits = []
                for w in words:
                    for sub in w.split(' y '):
                        clean = sub.replace('algo ', '').replace('muy ', '').strip().capitalize()
                        if clean and len(clean) > 3:
                            traits.append(clean)
                traits = traits[:3]
    return desc, traits

print(parse(text))
