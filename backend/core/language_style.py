import re
from typing import Dict, List, Any

class LanguageStyleDetector:
    """
    Analyzes incoming messages to detect:
    1. Languages (including code-switching)
    2. Communication Style (Formality, Emojis, Slang)
    """

    def __init__(self):
        # Regex patterns for language markers
        self.lang_patterns = {
            'swahili': [
                r'\b(habari|jambo|sasa|niaje|mambo|poa|asante|karibu|tafadhali|hapana|ndiyo|sawa|kwaheri|basi|bana|wazi)\b',
                r'\b(yako|wako|zako|cha|la|wa|ya)\b', # Possessives/Connectives
                r'\b(niko|uko|yuko|tuko|wako)\b' # 'To be' verbs
            ],
            'sheng': [
                r'\b(form|rada|mbogi|ngwai|chali|manzi|buda|jo|fiti|maasai|dooh|chapaa|ganji)\b',
                r'\b(unaleta|unadai|unataka)\b'
            ],
            'english': [
                r'\b(hello|hi|hey|how|are|you|thanks|please|yes|no|good|bad|help|want|need|order)\b',
                r'\b(the|is|in|at|on|for|to|of|and|but|or|so)\b'
            ],
            'spanish': [
                r'\b(hola|gracias|por favor|si|no|buenos|dias|noches|amigo|usted|tu|que|como|estas)\b'
            ],
            'french': [
                r'\b(bonjour|salut|merci|oui|non|s\'il|vous|plait|comment|ca|va|monsieur|madame)\b'
            ]
        }

        # Communication style markers
        self.formal_markers = [
            r'\b(dear|sir|madam|regards|sincerely|kindly|please|assist|inquire|regarding|appreciate|gratitude)\b'
        ]
        
        self.casual_markers = [
            r'\b(hey|hi|yo|sup|bro|dude|fam|gonna|wanna|kinda|lol|lmao|omg|btw|idk)\b'
        ]

        self.slang_markers = [
            r'\b(gonna|wanna|gotta|lemme|dunno|aint|innit)\b',
            # Add more region-specific slang if needed
        ]

    def analyze(self, message: str) -> Dict[str, Any]:
        """
        Main analysis method.
        Returns a dictionary with language profile and style metrics.
        """
        if not message:
            return self._default_profile()

        text = message.lower()
        
        # 1. Detect Languages & Code Switching
        detected_langs = self._detect_languages(text)
        primary_lang = max(detected_langs, key=detected_langs.get) if detected_langs else 'english'
        
        # Determine code-switching
        active_langs = [lang for lang, score in detected_langs.items() if score > 0]
        is_code_switching = len(active_langs) > 1

        # 2. Analyze Style
        formality_score = self._calculate_formality(text)
        emoji_analysis = self._analyze_emojis(message) # Use original message for case/emoji detection
        slang_score = self._calculate_slang_usage(text)
        
        style_type = 'neutral'
        if formality_score > 0.3:
            style_type = 'formal'
        elif formality_score < -0.3 or slang_score > 0.2:
            style_type = 'casual'

        return {
            'language': {
                'primary': primary_lang,
                'detected': detected_langs,
                'is_mixed': is_code_switching,
                'mix_type': '+'.join(sorted(active_langs)) if is_code_switching else primary_lang
            },
            'style': {
                'type': style_type, # formal, casual, neutral
                'formality_score': formality_score, # -1 (very casual) to 1 (very formal)
                'slang_score': slang_score,
                'emoji_usage': emoji_analysis
            }
        }

    def _detect_languages(self, text: str) -> Dict[str, float]:
        scores = {lang: 0.0 for lang in self.lang_patterns}
        words = re.findall(r'\w+', text)
        total_words = len(words)
        
        if total_words == 0:
            return scores

        for lang, patterns in self.lang_patterns.items():
            count = 0
            for pattern in patterns:
                count += len(re.findall(pattern, text))
            scores[lang] = count / total_words if total_words > 0 else 0
            
        return scores

    def _calculate_formality(self, text: str) -> float:
        formal_count = sum(len(re.findall(p, text)) for p in self.formal_markers)
        casual_count = sum(len(re.findall(p, text)) for p in self.casual_markers)
        
        total_markers = formal_count + casual_count
        if total_markers == 0:
            return 0.0
            
        # Returns value between -1 (casual) and 1 (formal)
        return (formal_count - casual_count) / total_markers

    def _analyze_emojis(self, text: str) -> Dict[str, Any]:
        # Regex range for common emojis
        emoji_pattern = re.compile(r'[\U0001F000-\U0001FAFF]')
        emojis = emoji_pattern.findall(text)
        
        count = len(emojis)
        has_emojis = count > 0
        
        return {
            'has_emojis': has_emojis,
            'count': count,
            'frequency': 'high' if count > 2 else ('low' if count > 0 else 'none'),
            'used': list(set(emojis)) # Unique emojis used
        }

    def _calculate_slang_usage(self, text: str) -> float:
        slang_count = sum(len(re.findall(p, text)) for p in self.slang_markers)
        # Also include Sheng as slang influence
        sheng_count = sum(len(re.findall(p, text)) for p in self.lang_patterns['sheng'])
        
        words = len(re.findall(r'\w+', text))
        if words == 0:
            return 0.0
            
        return (slang_count + sheng_count) / words

    def _default_profile(self) -> Dict[str, Any]:
        return {
            'language': {'primary': 'english', 'detected': {}, 'is_mixed': False, 'mix_type': 'english'},
            'style': {'type': 'neutral', 'formality_score': 0, 'slang_score': 0, 'emoji_usage': {'has_emojis': False, 'count': 0, 'frequency': 'none', 'used': []}}
        }
