from typing import Dict, List, Optional

try:
    from ubigeos_peru import cargar_diccionario
except Exception:
    cargar_diccionario = None

DEPARTAMENTO_OPERATIVO = 'Junín'
PROVINCIA_INICIAL = 'Huancayo'
DISTRITO_INICIAL = 'Huancayo'
UBIGEO_INICIAL = '120101'

_CACHE: Optional[Dict[str, object]] = None

_FALLBACK_PROVINCIAS = [
    'Huancayo',
    'Concepción',
    'Chanchamayo',
    'Jauja',
    'Junín',
    'Satipo',
    'Tarma',
    'Yauli',
    'Chupaca',
]

_FALLBACK_DISTRITOS = {
    'Huancayo': ['Huancayo', 'El Tambo', 'Chilca'],
    'Concepción': ['Concepción'],
    'Chanchamayo': ['Chanchamayo', 'Pichanaqui'],
    'Jauja': ['Jauja'],
    'Junín': ['Junín'],
    'Satipo': ['Satipo', 'Pangoa'],
    'Tarma': ['Tarma'],
    'Yauli': ['La Oroya'],
    'Chupaca': ['Chupaca'],
}

_FALLBACK_UBIGEOS = {
    'Junín|Huancayo|Huancayo': '120101',
    'Junín|Huancayo|El Tambo': '120114',
    'Junín|Huancayo|Chilca': '120107',
    'Junín|Concepción|Concepción': '120201',
    'Junín|Chanchamayo|Chanchamayo': '120302',
    'Junín|Chanchamayo|Pichanaqui': '120305',
    'Junín|Jauja|Jauja': '120401',
    'Junín|Junín|Junín': '120501',
    'Junín|Satipo|Satipo': '120601',
    'Junín|Satipo|Pangoa': '120605',
    'Junín|Tarma|Tarma': '120701',
    'Junín|Yauli|La Oroya': '120801',
    'Junín|Chupaca|Chupaca': '120901',
}


def _cache_fallback() -> Dict[str, object]:
    return {
        'departamentos': [DEPARTAMENTO_OPERATIVO],
        'provincias_por_departamento': {
            DEPARTAMENTO_OPERATIVO: list(_FALLBACK_PROVINCIAS),
        },
        'distritos_por_provincia': dict(_FALLBACK_DISTRITOS),
        'ubigeos': dict(_FALLBACK_UBIGEOS),
        'defaults': {
            'departamento': DEPARTAMENTO_OPERATIVO,
            'provincia': PROVINCIA_INICIAL,
            'distrito': DISTRITO_INICIAL,
            'ubigeo': UBIGEO_INICIAL,
        },
    }


def _construir_cache() -> Dict[str, object]:
    if cargar_diccionario is None:
        return _cache_fallback()

    departamentos = cargar_diccionario('departamentos')['inei']
    provincias = cargar_diccionario('provincias')['inei']
    distritos = cargar_diccionario('distritos')['inei']

    try:
        departamento_code = next(
            code for code, name in departamentos.items() if name == DEPARTAMENTO_OPERATIVO
        )
    except StopIteration:
        return _cache_fallback()

    provincias_de_junin = {
        code: name for code, name in provincias.items() if code.startswith(departamento_code)
    }

    provincias_por_departamento: Dict[str, List[str]] = {
        DEPARTAMENTO_OPERATIVO: [
            name for code, name in sorted(provincias_de_junin.items(), key=lambda item: item[0])
        ]
    }

    distritos_por_provincia: Dict[str, List[str]] = {}
    ubigeos: Dict[str, str] = {}

    for provincia_code, provincia_name in sorted(provincias_de_junin.items(), key=lambda item: item[0]):
        distritos_de_provincia = {
            code: name for code, name in distritos.items() if code.startswith(provincia_code)
        }
        distritos_por_provincia[provincia_name] = [
            name for code, name in sorted(distritos_de_provincia.items(), key=lambda item: item[0])
        ]
        for distrito_code, distrito_name in sorted(distritos_de_provincia.items(), key=lambda item: item[0]):
            ubigeos[f'{DEPARTAMENTO_OPERATIVO}|{provincia_name}|{distrito_name}'] = distrito_code

    return {
        'departamentos': [DEPARTAMENTO_OPERATIVO],
        'provincias_por_departamento': provincias_por_departamento,
        'distritos_por_provincia': distritos_por_provincia,
        'ubigeos': ubigeos,
        'defaults': {
            'departamento': DEPARTAMENTO_OPERATIVO,
            'provincia': PROVINCIA_INICIAL,
            'distrito': DISTRITO_INICIAL,
            'ubigeo': UBIGEO_INICIAL,
        },
    }


def _get_cache() -> Dict[str, object]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _construir_cache()
    return _CACHE


def obtener_departamentos() -> List[str]:
    return list(_get_cache()['departamentos'])


def obtener_provincias(departamento: str) -> List[str]:
    cache = _get_cache()
    return list(cache['provincias_por_departamento'].get(departamento, []))


def obtener_distritos(provincia: str) -> List[str]:
    cache = _get_cache()
    return list(cache['distritos_por_provincia'].get(provincia, []))


def obtener_ubigeo(departamento: str, provincia: str, distrito: str) -> str:
    clave = f'{departamento}|{provincia}|{distrito}'
    return _get_cache()['ubigeos'].get(clave, UBIGEO_INICIAL)


def obtener_todo_ubigeos() -> Dict[str, object]:
    return dict(_get_cache())
