import streamlit as st
import pandas as pd
from io import BytesIO
import plotly.graph_objects as go
import trimesh
import base64
import streamlit.components.v1 as components

# ✅ Kullanıcı giriş kontrolü
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.error("🔒 You must be logged in to access this page.")
    st.stop()

st.set_page_config(page_title="COMPADDITIVE Material Selection", layout="wide")
st.title("COMPADDITIVE Material Selection")

# ---------------------------
# 📋 Özellik listesi
# ---------------------------
properties = [
    "Coefficient of Thermal Expansion (CTE) (µstrain/°C)",
    "Cost (USD/kg)",
    "Heat Deflection Temperature A (1.8 MPa) (°C)",
    "Heat Deflection Temperature B (0.46 MPa) (°C)",
    "Interfacial Properties with Carbon Fiber (IFSS, MPa)",
    "Shrinkage (%)",
    "Tensile Strength (MPa)",
    "Flexural Modulus (GPa)",
    "Elongation At Break (%)",
    "Density (kg/m³)",
    "Glass Transition Temperature (°C)",
    "Melting Temperature (°C)",
    "Processing Temperature (°C)",
    "Injection Pressure (MPa)"
]

# ---------------------------
# 📁 Gömülü veri seti (aynı veri)
# ---------------------------
if "datasets" not in st.session_state:
    st.session_state.datasets = {
        "PEKK UNFILLED": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (21, 77),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (139, 185),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (150, 277),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (0.5, 1.6),
            "Tensile Strength (MPa)": (40.6, 111),
            "Flexural Modulus (GPa)": (2.50, 5.54),
            "Elongation At Break (%)": (0.58, 4.89),
            "Density (kg/m³)": (1270, 1310),
            "Glass Transition Temperature (°C)": (149, 160),
            "Melting Temperature (°C)": (300, 360),
            "Processing Temperature (°C)": (350, 400),
            "Injection Pressure (MPa)": (103, 138)
        },
        "PEKK 20-40% CF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (9, 45),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (202, 327),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (0.05, 0.3),
            "Tensile Strength (MPa)": (59, 324),
            "Flexural Modulus (GPa)": (5.13, 31),
            "Elongation At Break (%)": (1.06, 2.5),
            "Density (kg/m³)": (1360, 1620),
            "Glass Transition Temperature (°C)": (160, 160),
            "Melting Temperature (°C)": (302, 360),
            "Processing Temperature (°C)": (350, 400),
            "Injection Pressure (MPa)": (103, 138)
        },
        "PEEK UNFILLED": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (40, 60),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (140, 161),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (152, 210),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (1.1, 1.1),
            "Tensile Strength (MPa)": (70, 100),
            "Flexural Modulus (GPa)": (3.7, 3.9),
            "Elongation At Break (%)": (1.7, 25.8),
            "Density (kg/m³)": (1270, 1320),
            "Glass Transition Temperature (°C)": (143, 143),
            "Melting Temperature (°C)": (334, 334),
            "Processing Temperature (°C)": (100, 290),
            "Injection Pressure (MPa)": (82.7, 124)
        },
        "PEEK 30% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (15, 20),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (290, 315),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (0.2, 1.0),
            "Tensile Strength (MPa)": (150, 180),
            "Flexural Modulus (GPa)": (9.0, 10.3),
            "Elongation At Break (%)": (1.0, 3.0),
            "Density (kg/m³)": (1490, 1540),
            "Glass Transition Temperature (°C)": (143, 143),
            "Melting Temperature (°C)": (334, 334),
            "Processing Temperature (°C)": (100, 287),
            "Injection Pressure (MPa)": (6.9, 102)
        },
        "PEEK 30% CF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (15, 40),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (315, 320),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (323, 323),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (0.1, 0.4),
            "Tensile Strength (MPa)": (200, 220),
            "Flexural Modulus (GPa)": (13.0, 20.0),
            "Elongation At Break (%)": (1.0, 3.0),
            "Density (kg/m³)": (1440, 1440),
            "Glass Transition Temperature (°C)": (143, 143),
            "Melting Temperature (°C)": (334, 334),
            "Processing Temperature (°C)": (100, 310),
            "Injection Pressure (MPa)": (82.7, 124)
        },
        "PEEK 5-60% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (3.24, 99.7),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (157, 292),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (260, 302),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (0.05, 0.5),
            "Tensile Strength (MPa)": (80, 220),
            "Flexural Modulus (GPa)": (3.8, 55.0),
            "Elongation At Break (%)": (0.7, 3.99),
            "Density (kg/m³)": (1300, 1930),
            "Glass Transition Temperature (°C)": (143, 178),
            "Melting Temperature (°C)": (334, 334),
            "Processing Temperature (°C)": (100, 287),
            "Injection Pressure (MPa)": (6.9, 102)
        },
        "PEEK 10-60% CF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (1.80, 60.0),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (150, 294),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (274, 310),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (0.2, 2.2),
            "Tensile Strength (MPa)": (75, 2070),
            "Flexural Modulus (GPa)": (2.12, 159.0),
            "Elongation At Break (%)": (0.860, 7.0),
            "Density (kg/m³)": (1320, 1900),
            "Glass Transition Temperature (°C)": (143, 170),
            "Melting Temperature (°C)": (334, 334),
            "Processing Temperature (°C)": (100, 294),
            "Injection Pressure (MPa)": (82.7, 124)
        },
        "PEEK 5-45% PTFE": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (9.0, 65.0),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (149, 325),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (0.1, 2.5),
            "Tensile Strength (MPa)": (64, 155),
            "Flexural Modulus (GPa)": (2.41, 14.0),
            "Elongation At Break (%)": (0.9, 3.0),
            "Density (kg/m³)": (1320, 1690),
            "Glass Transition Temperature (°C)": (143, 170),
            "Melting Temperature (°C)": (340, 385),
            "Processing Temperature (°C)": (100, 340),
            "Injection Pressure (MPa)": (49.6, 124)
        },
        "PEEK ARAMID FIBER": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (5.0, 10.0),
            "Cost (USD/kg)": (54.50, 81.75),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (163, 260),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (80.0, 80.0),
            "Shrinkage (%)": (0.05, 1.50),
            "Tensile Strength (MPa)": (75.0, 193),
            "Flexural Modulus (GPa)": (4.83, 22.8),
            "Elongation At Break (%)": (1.00, 6.00),
            "Density (kg/m³)": (1310, 1500),
            "Glass Transition Temperature (°C)": (143, 170),
            "Melting Temperature (°C)": (349, 399),
            "Processing Temperature (°C)": (343, 388),
            "Injection Pressure (MPa)": (82.7, 124)
        },
        "PESU UNFILLED": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (27, 60),
            "Cost (USD/kg)": (7.63, 13.08),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (195, 204),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (50.0, 50.0),
            "Shrinkage (%)": (0.6, 0.7),
            "Tensile Strength (MPa)": (70, 95),
            "Flexural Modulus (GPa)": (2.4, 2.9),
            "Elongation At Break (%)": (0, 6),
            "Density (kg/m³)": (1370, 1400),
            "Glass Transition Temperature (°C)": (210, 230),
            "Melting Temperature (°C)": (288, 410),
            "Processing Temperature (°C)": (80, 297),
            "Injection Pressure (MPa)": (3.45, 103)
        },
        "PESU 10% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (25.0, 50.4),
            "Cost (USD/kg)": (7.63, 13.08),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (204, 216),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (207, 220),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (50.0, 50.0),
            "Shrinkage (%)": (0.1, 0.8),
            "Tensile Strength (MPa)": (66.9, 135),
            "Flexural Modulus (GPa)": (3.45, 8.62),
            "Elongation At Break (%)": (1.90, 8.0),
            "Density (kg/m³)": (1390, 1580),
            "Glass Transition Temperature (°C)": (225, 225),
            "Melting Temperature (°C)": (340, 399),
            "Processing Temperature (°C)": (343, 366),
            "Injection Pressure (MPa)": (68.9, 103)
        },
        "PESU 20% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (20.0, 39.6),
            "Cost (USD/kg)": (7.63, 13.08),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (204, 220),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (210, 224),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (50.0, 50.0),
            "Shrinkage (%)": (0.1, 0.8),
            "Tensile Strength (MPa)": (81.4, 150),
            "Flexural Modulus (GPa)": (3.79, 6.89),
            "Elongation At Break (%)": (1.50, 5.0),
            "Density (kg/m³)": (1470, 1620),
            "Glass Transition Temperature (°C)": (225, 225),
            "Melting Temperature (°C)": (343, 390),
            "Processing Temperature (°C)": (80, 366),
            "Injection Pressure (MPa)": (68.9, 103)
        },
        "PESU 30% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (15.0, 36.0),
            "Cost (USD/kg)": (7.63, 13.08),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (204, 220),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (215, 222),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (50.0, 50.0),
            "Shrinkage (%)": (0.1, 0.5),
            "Tensile Strength (MPa)": (60.0, 150),
            "Flexural Modulus (GPa)": (7.58, 11.3),
            "Elongation At Break (%)": (1.40, 4.0),
            "Density (kg/m³)": (1460, 1700),
            "Glass Transition Temperature (°C)": (225, 225),
            "Melting Temperature (°C)": (343, 390),
            "Processing Temperature (°C)": (343, 366),
            "Injection Pressure (MPa)": (68.9, 103)
        },
        "PPS UNFILLED": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (30, 50),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (100, 135),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (170, 200),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.6, 1.4),
            "Tensile Strength (MPa)": (50, 80),
            "Flexural Modulus (GPa)": (3.8, 4.2),
            "Elongation At Break (%)": (1.0, 4.0),
            "Density (kg/m³)": (1350, 1350),
            "Glass Transition Temperature (°C)": (88, 93),
            "Melting Temperature (°C)": (275, 290),
            "Processing Temperature (°C)": (20, 340),
            "Injection Pressure (MPa)": (34.5, 103)
        },
        "PPS 10% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (10.00, 50.00),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (115, 275),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (260, 282),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.3, 1.0),
            "Tensile Strength (MPa)": (34.5, 375),
            "Flexural Modulus (GPa)": (4.83, 21.0),
            "Elongation At Break (%)": (0.8, 3.5),
            "Density (kg/m³)": (1380, 2060),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (280, 285),
            "Processing Temperature (°C)": (288, 330),
            "Injection Pressure (MPa)": (30, 103)
        },
        "PPS 20% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (12.0, 60.0),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (165, 275),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (246, 280),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.05, 0.8),
            "Tensile Strength (MPa)": (86.0, 162),
            "Flexural Modulus (GPa)": (5.10, 25.0),
            "Elongation At Break (%)": (0.860, 3.0),
            "Density (kg/m³)": (1300, 2530),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (20, 340),
            "Processing Temperature (°C)": (20, 340),
            "Injection Pressure (MPa)": (30, 103)
        },
        "PPS 30% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (9.00, 120),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (105, 272),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (200, 280),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.02, 1.20),
            "Tensile Strength (MPa)": (33.1, 203),
            "Flexural Modulus (GPa)": (1.20, 30.1),
            "Elongation At Break (%)": (0.5, 4.0),
            "Density (kg/m³)": (1400, 1690),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (260, 282),
            "Processing Temperature (°C)": (20, 340),
            "Injection Pressure (MPa)": (30, 103)
        },
        "PPS 40% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (10.00, 135),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (98.9, 282),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (250, 282),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.05, 1.00),
            "Tensile Strength (MPa)": (32.4, 220),
            "Flexural Modulus (GPa)": (3.10, 34.9),
            "Elongation At Break (%)": (0.5, 4.0),
            "Density (kg/m³)": (1350, 1800),
            "Glass Transition Temperature (°C)": (88, 90),
            "Melting Temperature (°C)": (278, 310),
            "Processing Temperature (°C)": (20, 350),
            "Injection Pressure (MPa)": (30, 150)
        },
        "PPS 50% GF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (7.00, 45.00),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (258, 282),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (266, 280),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.05, 1.00),
            "Tensile Strength (MPa)": (94.0, 179.953),
            "Flexural Modulus (GPa)": (10.3, 39.2),
            "Elongation At Break (%)": (0.4, 2.20),
            "Density (kg/m³)": (1530, 1900),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (280, 285),
            "Processing Temperature (°C)": (70, 340),
            "Injection Pressure (MPa)": (30, 103)
        },
        "PPS 10% CF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (5.00, 32.00),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (232, 280),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (260, 285),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.1, 0.86),
            "Tensile Strength (MPa)": (67.6, 680),
            "Flexural Modulus (GPa)": (0.552, 57.0),
            "Elongation At Break (%)": (0.5, 5.96),
            "Density (kg/m³)": (1290, 1960),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (278, 285),
            "Processing Temperature (°C)": (285, 350),
            "Injection Pressure (MPa)": (30, 124)
        },
        "PPS 20% CF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (15.0, 20.0),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (260, 275),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.02, 0.25),
            "Tensile Strength (MPa)": (27.6, 186),
            "Flexural Modulus (GPa)": (8.27, 18.6),
            "Elongation At Break (%)": (0.3, 2.5),
            "Density (kg/m³)": (1350, 1540),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (278, 280),
            "Processing Temperature (°C)": (290, 343),
            "Injection Pressure (MPa)": (68.9, 124)
        },
        "PPS 30% CF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (5.00, 20.00),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (255, 280),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.02, 0.6),
            "Tensile Strength (MPa)": (46.9, 236),
            "Flexural Modulus (GPa)": (8.00, 32.00),
            "Elongation At Break (%)": (0.5, 3.0),
            "Density (kg/m³)": (1410, 1580),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (278, 280),
            "Processing Temperature (°C)": (288, 340),
            "Injection Pressure (MPa)": (30, 124)
        },
        "PPS 40% CF": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (5.0, 10.0),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (260, 280),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (260, 280),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.05, 0.60),
            "Tensile Strength (MPa)": (77.2, 234),
            "Flexural Modulus (GPa)": (11.0, 35.0),
            "Elongation At Break (%)": (0, 2.0),
            "Density (kg/m³)": (1480, 1720),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (278, 280),
            "Processing Temperature (°C)": (288, 330),
            "Injection Pressure (MPa)": (30, 103)
        },
        "PPS 10-40% CF + PTFE": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (9.00, 60.00),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (152, 277),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (260, 280),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.01, 0.50),
            "Tensile Strength (MPa)": (53.0, 180),
            "Flexural Modulus (GPa)": (9.00, 27.6),
            "Elongation At Break (%)": (0, 2.0),
            "Density (kg/m³)": (1080, 1620),
            "Glass Transition Temperature (°C)": (90, 94),
            "Melting Temperature (°C)": (278, 281),
            "Processing Temperature (°C)": (288, 370),
            "Injection Pressure (MPa)": (30, 103)
        },
        "PPS CONDUCTIVE": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (19.80, 19.80),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (220, 268),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (260, 274),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0, 0.60),
            "Tensile Strength (MPa)": (45.0, 172),
            "Flexural Modulus (GPa)": (0.552, 25.5),
            "Elongation At Break (%)": (0.30, 6.78),
            "Density (kg/m³)": (1290, 3700),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (280, 290),
            "Processing Temperature (°C)": (307, 329),
            "Injection Pressure (MPa)": (68.9, 103)
        },
        "PPS 25-65% GF + MINERAL": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (10.00, 250.0),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (175, 280),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (250, 285),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.100, 1.00),
            "Tensile Strength (MPa)": (42.1, 197),
            "Flexural Modulus (GPa)": (7.00, 14.00),
            "Elongation At Break (%)": (0.5, 2.00),
            "Density (kg/m³)": (1530, 2110),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (230, 285),
            "Processing Temperature (°C)": (20, 340),
            "Injection Pressure (MPa)": (4.96, 150)
        },
        "PPS STAINLESS STEEL FIBER": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (20.0, 30.0),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (254, 260),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.2, 1.6),
            "Tensile Strength (MPa)": (47.0, 145),
            "Flexural Modulus (GPa)": (4.00, 17.9),
            "Elongation At Break (%)": (1.00, 2.00),
            "Density (kg/m³)": (1410, 1790),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (278, 280),
            "Processing Temperature (°C)": (307, 329),
            "Injection Pressure (MPa)": (68.9, 103)
        },
        "PPS 10-50% GF + PTFE": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (10.8, 32.4),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (232, 277),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (260, 280),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.05, 0.80),
            "Tensile Strength (MPa)": (26.2, 180),
            "Flexural Modulus (GPa)": (4.90, 17.9),
            "Elongation At Break (%)": (0.800, 3.00),
            "Density (kg/m³)": (1410, 1870),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (278, 284),
            "Processing Temperature (°C)": (288, 370),
            "Injection Pressure (MPa)": (4.96, 124)
        },
        "PPS 10-70% PTFE": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (50.0, 100.0),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (93, 270),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": None,
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.20, 2.00),
            "Tensile Strength (MPa)": (11.0, 160),
            "Flexural Modulus (GPa)": (1.31, 15.0),
            "Elongation At Break (%)": (0.50, 5.04),
            "Density (kg/m³)": (1420, 2030),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (278, 280),
            "Processing Temperature (°C)": (280, 343),
            "Injection Pressure (MPa)": (30.0, 103)
        },
        "PPS 10-30% ARAMID FIBER": {
            "Coefficient of Thermal Expansion (CTE) (µstrain/°C)": (10.0, 15.0),
            "Cost (USD/kg)": (7.63, 14.17),
            "Heat Deflection Temperature A (1.8 MPa) (°C)": (110, 260),
            "Heat Deflection Temperature B (0.46 MPa) (°C)": (249, 271),
            "Interfacial Properties with Carbon Fiber (IFSS, MPa)": (40.0, 40.0),
            "Shrinkage (%)": (0.05, 1.40),
            "Tensile Strength (MPa)": (45.0, 134),
            "Flexural Modulus (GPa)": (3.50, 20.7),
            "Elongation At Break (%)": (1.00, 4.00),
            "Density (kg/m³)": (1250, 1560),
            "Glass Transition Temperature (°C)": (90, 90),
            "Melting Temperature (°C)": (285, 343),
            "Processing Temperature (°C)": (140, 321),
            "Injection Pressure (MPa)": (68.9, 138)
        }
    }

# ---------------------------
# 🔧 Yardımcı: Excel şablonu
# ---------------------------
def generate_excel_template():
    columns = ["Name"]
    for prop in properties:
        columns.append(f"{prop} min")
        columns.append(f"{prop} max")
    df_template = pd.DataFrame(columns=columns)
    output = BytesIO()
    with pd.ExcelWriter(output) as writer:
        df_template.to_excel(writer, index=False, sheet_name='Template')
    output.seek(0)
    return output

# ---------------------------
# 🗂️ Sekmeler
# ---------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📂 Dataset Management",
    "🚩 Pre-Screening",
    "🔎 Filtering",
    "⚖️ Weighted Scoring",
    "💰 Mold Cost Analysis"
])

# =========================================================
# TAB 1 — DATASET MANAGEMENT
# =========================================================
with tab1:
    option = st.radio("Choose how you would like to proceed:", [
        "Use embedded dataset",
        "Add manual entry",
        "Upload dataset from Excel"
    ], key="dataset_option")

    # 🔧 Manuel giriş
    if option == "Add manual entry":
        new_entry = {}
        composite_name = st.text_input("Enter the name of the new composite")

        for prop in properties:
            col1, col2 = st.columns(2)
            with col1:
                min_val = st.number_input(f"Min. {prop}", key=f"min_{prop}")
            with col2:
                max_val = st.number_input(f"Max. {prop}", key=f"max_{prop}")
            new_entry[prop] = (min_val, max_val)

        if st.button("Add composite to dataset"):
            if composite_name and all(isinstance(val, tuple) for val in new_entry.values()):
                st.session_state.datasets[composite_name] = new_entry
                st.success(f"✅ {composite_name} added successfully.")

    # 📥 Excel'den yükleme
    elif option == "Upload dataset from Excel":
        st.info("""📄 Please download the template, fill in your data, and upload it back.

- Include values for all properties.
- Do **not change column names**.

📥 You can download the blank Excel file using the button below.""")

        st.download_button(
            label="📥 Download Excel Template",
            data=generate_excel_template(),
            file_name="composite_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        uploaded_file = st.file_uploader("Upload your completed Excel file here", type=["xlsx"])
        if uploaded_file:
            df = pd.read_excel(uploaded_file)
            for idx, row in df.iterrows():
                name = row["Name"]
                entry = {}
                for prop in properties:
                    entry[prop] = (row[f"{prop} min"], row[f"{prop} max"])
                st.session_state.datasets[name] = entry
            st.success("✅ All composites from the Excel file uploaded successfully.")

    # 📌 CANDIDATE COMPOSITES — Tüm kompozitleri yatay tabloda göster
    if st.session_state.datasets:
        st.markdown("### **Candidate Composites**")
        all_data = {}
        for name, prop_dict in st.session_state.datasets.items():
            all_data[name] = {}
            for prop in properties:
                val = prop_dict.get(prop)
                if val is None:
                    all_data[name][prop] = "N/A"
                elif isinstance(val, tuple):
                    all_data[name][prop] = f"{val[0]} – {val[1]}"
                else:
                    all_data[name][prop] = str(val)
        df_candidates = pd.DataFrame(all_data)
        st.dataframe(df_candidates, use_container_width=True)

# =========================================================
# TAB 2 — PRE-SCREENING
# =========================================================
with tab2:
    # 📄 Ön Eleme Kriterleri Bilgilendirme Yazısı
    st.markdown("### 📌 Pre-Screening Criteria")
    st.markdown("""
    1. The **CTE of the composite** must be compatible with the **CTE of CFRP epoxy** with a **maximum variation of 60%**.  
    2. The **cost of the composite** must be **at least 30% lower than the cost of Invar** in terms of **euro/m³**.  
    3. The **composite must not undergo plastic deformation** under **autoclave conditions (180°C and 7 bar)**.
    """)

    # --- Sabitler ---
    epoxy_cte = 50  # µstrain/°C
    usd_to_eur = 0.91
    invar_cost_usd_per_kg = 70
    invar_density = 8000
    invar_cost_eur_per_m3 = invar_cost_usd_per_kg * invar_density * usd_to_eur
    threshold_cost = invar_cost_eur_per_m3 * 0.70  # %30 daha düşük olması gerekir

    passed_composites = []

    for name, props in st.session_state.datasets.items():
        # --- 1. KRİTER: CTE uyumu ---
        cte_range = props.get("Coefficient of Thermal Expansion (CTE) (µstrain/°C)")
        if not isinstance(cte_range, tuple):
            continue
        avg_cte = sum(cte_range) / 2
        cte_lower = epoxy_cte * (1 - 0.6)
        cte_upper = epoxy_cte * (1 + 0.6)
        if not (cte_lower <= avg_cte <= cte_upper):
            continue

        # --- 2. KRİTER: Cost < Invar %30 ---
        cost_range = props.get("Cost (USD/kg)")
        density_range = props.get("Density (kg/m³)")
        if not isinstance(cost_range, tuple) or not isinstance(density_range, tuple):
            continue
        avg_cost = sum(cost_range) / 2
        avg_density = sum(density_range) / 2
        cost_eur_per_m3 = avg_cost * avg_density * usd_to_eur
        if cost_eur_per_m3 > threshold_cost:
            continue

        # --- 3. KRİTER: Otoklav deformasyon testi (N/A toleranslı kural) ---
        hdt_a = props.get("Heat Deflection Temperature A (1.8 MPa) (°C)")
        hdt_b = props.get("Heat Deflection Temperature B (0.46 MPa) (°C)")

        avg_hdt_a = None
        avg_hdt_b = None
        if isinstance(hdt_a, tuple):
            avg_hdt_a = sum(hdt_a) / 2
        if isinstance(hdt_b, tuple):
            avg_hdt_b = sum(hdt_b) / 2

        def passes_hdt_rule(avg_hdt_a, avg_hdt_b, min_required=180.0):
            # 1) Eğer A mevcut ve yeterince yüksekse → geçer
            if avg_hdt_a is not None and avg_hdt_a >= min_required:
                return True
            # 2) Eğer sadece B mevcutsa ve yeterince yüksekse → geçer
            if avg_hdt_b is not None and avg_hdt_b >= min_required:
                return True
            # 3) İkisi de varsa interpolasyon uygula
            if (avg_hdt_a is not None) and (avg_hdt_b is not None):
                interpolated_temp = avg_hdt_b + ((0.7 - 0.46) / (1.8 - 0.46)) * (avg_hdt_a - avg_hdt_b)
                return interpolated_temp >= min_required
            # 4) Veriler yetersiz → kalır
            return False

        if not passes_hdt_rule(avg_hdt_a, avg_hdt_b, min_required=180.0):
            continue

        # 🎯 Tüm kriterlerden geçti
        passed_composites.append(name)

    st.markdown("---")
    st.markdown("### ✅ **Pre-Screening Passed Composites**")

    if passed_composites:
        st.success(f"{len(passed_composites)} composites passed all three criteria:")
        st.markdown("**" + ", ".join(passed_composites) + "**")

        # 📊 Geçenleri tabloda göster
        filtered_data = {}
        for name in passed_composites:
            filtered_data[name] = {}
            for prop in properties:
                val = st.session_state.datasets[name].get(prop)
                if val is None:
                    filtered_data[name][prop] = "N/A"
                elif isinstance(val, tuple):
                    filtered_data[name][prop] = f"{val[0]} – {val[1]}"
                else:
                    filtered_data[name][prop] = str(val)
        df_passed = pd.DataFrame(filtered_data)
        st.dataframe(df_passed, use_container_width=True)
    else:
        st.warning("❌ No composites passed all three pre-screening criteria.")

    # Sonraki sekmelerin kullanabilmesi için sakla
    st.session_state["passed_composites"] = passed_composites
    
# =========================================================
# TAB 3 — FILTERING
# =========================================================
with tab3:
    filterable_props = [
        "Cost (USD/kg)",
        "Interfacial Properties with Carbon Fiber (IFSS, MPa)",
        "Shrinkage (%)",
        "Tensile Strength (MPa)",
        "Flexural Modulus (GPa)",
        "Elongation At Break (%)",
        "Density (kg/m³)",
        "Glass Transition Temperature (°C)",
        "Melting Temperature (°C)",
        "Processing Temperature (°C)",
        "Injection Pressure (MPa)"
    ]

    st.markdown("### 🔎 Property-Based Filtering")
    selected_filters = {}

    for prop in filterable_props:
        if st.checkbox(f"Filter by {prop}", key=f"chk_{prop}"):
            col1, col2 = st.columns([1, 2])
            with col1:
                condition = st.selectbox(
                    f"Condition for {prop}",
                    ["smaller than", "larger than", "equal to"],
                    key=f"cond_{prop}"
                )
            with col2:
                value = st.number_input(f"Value for {prop}", key=f"val_{prop}")
            selected_filters[prop] = (condition, value)

    # 🎯 Filtreleri geçenleri belirle (sadece pre-screening'i geçenler)
    filtered_composites = []
    base_pool = st.session_state.get("passed_composites", [])

    for name in base_pool:
        props = st.session_state.datasets[name]
        match = True
        for prop, (condition, user_val) in selected_filters.items():
            value_range = props.get(prop)
            if not isinstance(value_range, tuple):
                match = False
                break
            min_val, max_val = value_range
            if condition == "smaller than":
                if min_val > user_val:
                    match = False
                    break
            elif condition == "larger than":
                if max_val < user_val:
                    match = False
                    break
            elif condition == "equal to":
                if not (min_val <= user_val <= max_val):
                    match = False
                    break
        if match:
            filtered_composites.append(name)

    final_filtered_composites = filtered_composites

    st.markdown("---")
    st.markdown("### ✅ **Filtering Passed Composites**")
    if final_filtered_composites:
        st.success(f"{len(final_filtered_composites)} composites matched all selected filter conditions:")
        st.markdown("**" + ", ".join(final_filtered_composites) + "**")
    else:
        st.warning("❌ No composites matched the filtering criteria.")

    # Skor ve Maliyet sekmeleri için sakla
    st.session_state["selected_filters"] = selected_filters
    st.session_state["final_filtered_composites"] = final_filtered_composites

# =========================================================
# TAB 4 — WEIGHTED SCORING
# =========================================================
with tab4:
    selected_filters = st.session_state.get("selected_filters", {})
    final_filtered_composites = st.session_state.get("final_filtered_composites", [])

    if selected_filters and final_filtered_composites:
        st.subheader("⚖️ Set importance (weight) for each selected property")
        weights = {}
        total_weight = 0

        for prop in selected_filters.keys():
            weight = st.number_input(
                f"Weight for '{prop}' (0–100)",
                min_value=0,
                max_value=100,
                value=st.session_state.get(f"weight_{prop}", 0),
                step=1,
                key=f"weight_{prop}"
            )
            weights[prop] = weight
            total_weight += weight

        st.markdown(f"📊 **Total weight: {total_weight}/100**")

        if total_weight != 100:
            st.warning("⚠️ Total weight must be exactly 100 to proceed.")
        else:
            def evaluate_score(condition, user_val, min_val, max_val):
                if user_val is None or min_val is None or max_val is None:
                    return 0.0
                if min_val == max_val:
                    return 1.05 if user_val == min_val else max(0.0, 1 - abs(user_val - min_val) / (abs(min_val) if min_val != 0 else 1))
                range_val = max_val - min_val
                center = (min_val + max_val) / 2
                if condition == "smaller than":
                    if user_val <= min_val:
                        return 1.0
                    elif user_val > max_val:
                        return max(0.0, 1 - (user_val - max_val) / range_val)
                    else:
                        return 1 - (user_val - min_val) / range_val
                elif condition == "larger than":
                    if user_val >= max_val:
                        return 1.0
                    elif user_val < min_val:
                        return max(0.0, 1 - (min_val - user_val) / range_val)
                    else:
                        return 1 - (max_val - user_val) / range_val
                elif condition == "equal to":
                    diff = abs(user_val - center)
                    normalized = 1 - (diff / range_val)
                    return 1.05 if diff == 0 else max(0.0, normalized)
                return 0.0

            # 🔢 Skorları hesapla
            scores = {}
            contribution_table = {}

            for name in final_filtered_composites:
                total_score = 0
                contribution_table[name] = {}

                for prop, (condition, user_val) in selected_filters.items():
                    min_val, max_val = st.session_state.datasets[name].get(prop, (None, None))
                    score = evaluate_score(condition, user_val, min_val, max_val)
                    weight = weights[prop] / 100
                    total_score += score * weight
                    contribution_table[name][prop] = round(score * weight * 100, 2)

                scores[name] = round(total_score * 100, 2)

            # 🏆 Skorları sırala
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

            st.subheader("🏆 Ranked Composites by Weighted Scoring")
            for i, (name, score) in enumerate(sorted_scores, 1):
                st.write(f"{i}. **{name}** — Score: {score:.2f} / 100")

            # 📊 Stacked bar chart
            st.subheader("📊 Composite Score Breakdown")
            fig = go.Figure()
            sorted_names = [k for k, _ in sorted_scores]

            for prop in selected_filters.keys():
                y_vals = [contribution_table[name][prop] for name in sorted_names]
                hover_texts = [
                    f"{prop}<br>Contribution: {contribution_table[name][prop]}<br>Weight: {weights[prop]}"
                    for name in sorted_names
                ]
                fig.add_trace(go.Bar(
                    name=prop,
                    x=sorted_names,
                    y=y_vals,
                    hovertext=hover_texts,
                    hoverinfo="text"
                ))

            fig.update_layout(
                barmode='stack',
                xaxis_title="Composite",
                yaxis_title="Total Score (out of 100)",
                title="📊 Composite Score Breakdown",
                height=600
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ℹ️ Please complete Pre-Screening and Filtering tabs first, then set weights here.")

# =========================================================
# TAB 5 — MOLD COST ANALYSIS
# =========================================================
with tab5:
    final_filtered_composites = st.session_state.get("final_filtered_composites", [])

    with st.expander("💰 Calculate Mold Production Cost", expanded=True):
        st.markdown("Upload your STL file below. The volume and dimensions will be extracted automatically.")
        uploaded_stl = st.file_uploader("📦 Upload STL file", type=["stl"], key="stl_upload")

        if uploaded_stl and final_filtered_composites:
            try:
                mesh = trimesh.load(uploaded_stl, file_type='stl', force='mesh')
                volume_mm3 = mesh.volume
                volume_m3 = volume_mm3 * 1e-9
                bbox = mesh.bounding_box.extents
                bbox_mm = [round(x, 2) for x in bbox]
                
                st.success("✅ STL file successfully processed.")

                col1, col2, col3 = st.columns(3)
                col1.metric(label="Width (x)", value=f"{bbox_mm[0]} mm")
                col2.metric(label="Depth (y)", value=f"{bbox_mm[1]} mm")
                col3.metric(label="Height (z)", value=f"{bbox_mm[2]} mm")

                st.markdown("### Mold Volume")
                st.markdown(
                    f"<div style='font-size:20px; color:#4CAF50; font-weight:bold;'>{volume_m3:.8f} m³</div>",
                    unsafe_allow_html=True
                )

                # ✅ STL 3D ÖNİZLEME BÖLÜMÜ
                st.markdown("### 🧩 STL Preview (3D)")
                stl_bytes = uploaded_stl.getvalue()
                encoded = base64.b64encode(stl_bytes).decode()

                html_string = f"""
                <html>
                  <head>
                    <script src="https://cdn.jsdelivr.net/npm/three@0.112.1/build/three.min.js"></script>
                    <script src="https://cdn.jsdelivr.net/npm/three@0.112.1/examples/js/controls/OrbitControls.js"></script>
                    <script src="https://cdn.jsdelivr.net/npm/three@0.112.1/examples/js/loaders/STLLoader.js"></script>
                  </head>
                  <body>
                    <div id="container" style="width:100%; height:500px;"></div>
                    <script>
                      var scene = new THREE.Scene();
                      var camera = new THREE.PerspectiveCamera(75, window.innerWidth/window.innerHeight, 0.1, 1000);
                      var renderer = new THREE.WebGLRenderer();
                      renderer.setSize(window.innerWidth, 500);
                      document.getElementById("container").appendChild(renderer.domElement);

                      var controls = new THREE.OrbitControls(camera, renderer.domElement);

                      var loader = new THREE.STLLoader();
                      var dataUri = "data:application/octet-stream;base64,{encoded}";

                      loader.load(dataUri, function (geometry) {{
                          var material = new THREE.MeshNormalMaterial({{wireframe: false}});
                          var mesh = new THREE.Mesh(geometry, material);
                          geometry.computeBoundingBox();
                          var center = new THREE.Vector3();
                          geometry.boundingBox.getCenter(center);
                          mesh.position.sub(center);
                          scene.add(mesh);
                          camera.position.z = 100;
                          animate();
                      }});

                      function animate() {{
                          requestAnimationFrame(animate);
                          controls.update();
                          renderer.render(scene, camera);
                      }}
                    </script>
                  </body>
                </html>
                """
                components.html(html_string, height=550)

                # Üretim maliyetlerini hesapla
                results = []
                for name in final_filtered_composites:
                    props = st.session_state.datasets[name]
                    cost_range = props.get("Cost (USD/kg)")
                    density_range = props.get("Density (kg/m³)")

                    if not isinstance(cost_range, tuple) or not isinstance(density_range, tuple):
                        continue

                    avg_cost = sum(cost_range) / 2
                    avg_density = sum(density_range) / 2
                    mass = volume_m3 * avg_density
                    total_cost = mass * avg_cost

                    results.append({
                        "Composite": name,
                        "Average Density (kg/m³)": round(avg_density, 2),
                        "Average Cost (USD/kg)": round(avg_cost, 2),
                        "Estimated Mass (kg)": round(mass, 4),
                        "Estimated Production Cost (USD)": round(total_cost, 2)
                    })

                if results:
                    results_df = pd.DataFrame(results).sort_values(by="Estimated Production Cost (USD)").reset_index(drop=True)
                    st.markdown("### 💸 Estimated Mold Production Cost per Composite")

                    styled_df = results_df.style\
                        .format({
                            "Average Density (kg/m³)": "{:.0f}",
                            "Average Cost (USD/kg)": "{:.2f}",
                            "Estimated Mass (kg)": "{:.4f}",
                            "Estimated Production Cost (USD)": "${:.2f}"
                        })\
                        .set_properties(**{
                            "text-align": "center",
                            "font-family": "Arial",
                            "background-color": "#111",
                            "color": "white",
                            "border-color": "#444"
                        })\
                        .set_table_styles([{
                            "selector": "th",
                            "props": [
                                ("text-align", "center"),
                                ("background-color", "#222"),
                                ("color", "white"),
                                ("font-size", "14px")
                            ]
                        }])

                    st.dataframe(styled_df, use_container_width=True, height=400)
                else:
                    st.info("ℹ️ No valid composites to estimate cost. Please complete previous steps.")

            except Exception as e:
                st.error(f"❌ Error reading STL file: {e}")
        else:
            st.info("ℹ️ Please select composites in Filtering tab and upload an STL file to see cost analysis.")
