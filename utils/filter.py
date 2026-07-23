"""İlan alaka ve fiyat filtresi yardımcıları."""

import re


def _query_terms(query):
    """Arama sorgusunu normalize edip anlamlı kelimelere böler."""
    terms = re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", (query or "").lower(), flags=re.UNICODE)
    # 2 karakter altı terimleri gürültü sayıp at.
    return [t for t in terms if len(t) >= 2]


def relevance_score(listing, query):
    """
    Query terimlerinin başlıkta kaç kez geçtiğine göre puan döndürür.

    Ek olarak açıklama eşleşmelerini düşük ağırlıkla ekler.
    """
    terms = _query_terms(query)
    if not terms:
        return 0

    title = (listing.get("title") or "").lower()
    desc = (listing.get("description") or "").lower()

    score = 0
    for t in terms:
        score += title.count(t) * 3
        score += desc.count(t)
    return score


def is_relevant(listing, query):
    """
    İlan başlığında veya açıklamasında query kelimelerinden en az biri
    geçiyorsa True döndürür.
    """
    terms = _query_terms(query)
    if not terms:
        return True

    title = (listing.get("title") or "").lower()
    desc = (listing.get("description") or "").lower()
    text = f"{title} {desc}"
    return any(t in text for t in terms)


def filter_listings(listings, query, min_price_dkk=None, max_price_dkk=None):
    """
    İlan listesini alaka + DKK fiyat aralığına göre filtreler.

    - Alakasız ilanları eler.
    - min/max fiyat verilmişse fiyatı olmayan veya aralık dışı ilanları eler.
    """
    filtered = []
    for item in listings:
        if not is_relevant(item, query):
            continue

        price_dkk = item.get("price_dkk")
        if min_price_dkk is not None:
            if price_dkk is None or price_dkk < min_price_dkk:
                continue
        if max_price_dkk is not None:
            if price_dkk is None or price_dkk > max_price_dkk:
                continue

        filtered.append(item)

    return filtered
