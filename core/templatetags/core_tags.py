from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Retorna o valor de uma chave em um dicionário dentro do template.
    Garante suporte para chaves do tipo string ou int.
    """
    if not dictionary:
        return []
    val = dictionary.get(str(key))
    if val is None:
        val = dictionary.get(int(key))
    return val if val is not None else []
