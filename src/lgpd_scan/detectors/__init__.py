"""Detectores de dados pessoais: um módulo por tipo de dado."""

from lgpd_scan.detectors.base import Detector
from lgpd_scan.detectors.cnpj import detectar_cnpj
from lgpd_scan.detectors.cpf import detectar_cpf
from lgpd_scan.detectors.email import detectar_email
from lgpd_scan.detectors.telefone import detectar_telefone

DETECTORES: tuple[Detector, ...] = (
    detectar_cpf,
    detectar_cnpj,
    detectar_email,
    detectar_telefone,
)
