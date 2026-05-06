import re

from django.core.exceptions import ValidationError
from django.db.models import Q


def get_school_model():
    from .models import School
    return School


SCHOOL_REQUIRED_MESSAGE = "Вкажіть, будь ласка, свій навчальний заклад."
SCHOOL_INVALID_MESSAGE = "Такого навчального закладу не знайдено, будь ласка, напишіть правильно."

EDUCATION_KEYWORDS = (
    "школ",
    "ліцей",
    "лицей",
    "гімназ",
    "гимназ",
    "коледж",
    "college",
    "school",
    "lyceum",
    "gymnasium",
    "універс",
    "универс",
    "university",
    "інститут",
    "институт",
    "institute",
    "академ",
    "academy",
    "ззсо",
    "нвк",
    "хл",
    "зош",
    "зсш",
    "сш",
    "сзш",
    "спш",
)

GENERIC_EDUCATION_NAMES = {
    "школа",
    "school",
    "ліцей",
    "лицей",
    "гімназія",
    "гимназия",
    "коледж",
    "college",
    "університет",
    "университет",
    "university",
    "інститут",
    "институт",
    "academy",
    "академія",
    "академия",
    "зош",
    "зсш",
    "сш",
    "сзш",
}


def validate_school_name(value):
    school_name = (value or "").strip()
    if not school_name:
        raise ValidationError(SCHOOL_REQUIRED_MESSAGE)

    School = get_school_model()
    if School.objects.exists():
        # Спочатку шукаємо точний збіг (назва, коротка або str)
        all_schools = School.objects.all()
        for s in all_schools:
            if (str(s).lower() == school_name.lower() or 
                s.name.lower() == school_name.lower() or 
                (s.short_name and s.short_name.lower() == school_name.lower())):
                return str(s)

        # Якщо точного збігу немає, спробуємо знайти за логікою autocomplete
        words = school_name.lower().split()
        if len(words) > 0:
            # Спробуємо знайти школу, яка містить усі ці слова (або їх частини)
            # Це дозволить прийняти "ХЛ 112" як "Харківський ліцей №112"
            abbreviations = {'хл': 'харківський ліцей', 'хг': 'харківська гімназія', 'зош': 'школа'}
            expanded_words = []
            for w in words:
                if w in abbreviations:
                    expanded_words.extend(abbreviations[w].split())
                else:
                    expanded_words.append(w)
            
            q = Q()
            for w in expanded_words:
                if len(w) >= 2:
                    q &= (Q(name__icontains=w) | Q(short_name__icontains=w))
            
            fuzzy_match = School.objects.filter(q).first()
            if fuzzy_match:
                return str(fuzzy_match)
            
            # Спроба з пропуском першої літери (для друкарських помилок)
            if len(school_name) > 4:
                q_typo = Q()
                typo_words = [w[1:] if len(w) > 4 else w for w in words]
                for w in typo_words:
                    q_typo &= (Q(name__icontains=w) | Q(short_name__icontains=w))
                
                fuzzy_match = School.objects.filter(q_typo).first()
                if fuzzy_match:
                    return str(fuzzy_match)
        
        raise ValidationError("Цього навчального закладу немає у нашому списку. Оберіть варіант зі списку або зверніться до адміністратора.")

    school = school_name
    normalized = re.sub(r"\s+", " ", school)
    lower_value = normalized.lower()
    
    # Check if it's just a number (e.g. "112")
    if lower_value.isdigit() and 1 <= len(lower_value) <= 5:
        return normalized

    has_letter = bool(re.search(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", normalized))
    has_digit = bool(re.search(r"\d", normalized))
    tokens = [token for token in re.split(r"[\s,]+", normalized) if token]
    has_keyword = any(keyword in lower_value for keyword in EDUCATION_KEYWORDS)
    is_generic_name_only = lower_value in GENERIC_EDUCATION_NAMES
    looks_like_acronym_with_number = bool(
        re.search(r"\b[А-ЯІЇЄҐA-Z]{2,}\b", normalized) and has_digit
    )

    is_valid = (
        has_letter
        and (
            looks_like_acronym_with_number
            or (has_keyword and not is_generic_name_only)
            or (has_digit and len(normalized) < 10) # Allow "School 112" even if not in keywords (though school is a keyword)
        )
    )

    if not is_valid:
        raise ValidationError(SCHOOL_INVALID_MESSAGE)

    return normalized
