"""Universe definitions live outside the strategy. Swap or extend without touching logic.

Coverage targets round-the-clock opportunity flow:

* US equities (hundreds, NYSE + Nasdaq, all sectors)
* Nordic equities (Stockholm, Oslo, Copenhagen, Helsinki) and Frankfurt/Xetra
* Canada, UK, Australia, New Zealand, Japan, Hong Kong
* Bonds (treasury/credit ETFs + bond futures)
* FX majors, minors and Nordic crosses
* Futures: equity index, rates, energy, metals, agriculture
* Crypto majors — deliberately risk-gated, see ScanConfig.crypto_max_active_securities
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Symbol:
    ticker: str
    exchange: str
    country: str
    sector: str = "Unknown"
    name: str = ""
    asset_class: str = "equity"   # equity | bond | forex | future | crypto

    def provider_ticker(self, suffix: str = "") -> str:
        return f"{self.ticker}{suffix}" if suffix and not self.ticker.endswith(suffix) else self.ticker


@dataclass
class Universe:
    key: str
    label: str
    exchange: str
    symbols: List[Symbol] = field(default_factory=list)
    asset_class: str = "equity"

    def tickers(self) -> List[str]:
        return [s.ticker for s in self.symbols]


def _rows(exchange: str, country: str, sector: str, tickers: str, asset_class: str = "equity") -> List[Symbol]:
    """Compact bulk constructor: whitespace/comma separated tickers sharing sector + venue."""
    out: List[Symbol] = []
    for raw in tickers.replace(",", " ").split():
        out.append(Symbol(raw.strip(), exchange, country, sector, "", asset_class))
    return out


# ---------------------------------------------------------------------------------
# United States — hundreds of names, sector tagged for exposure limits
# ---------------------------------------------------------------------------------
US_TECH = _rows("NASDAQ", "US", "Technology", """
    AAPL MSFT NVDA AVGO AMD ADBE CRM ORCL CSCO ACN INTC QCOM TXN AMAT MU LRCX KLAC
    ADI SNPS CDNS PANW CRWD FTNT ZS OKTA DDOG NET SNOW MDB TEAM WDAY NOW INTU ANET
    SMCI ARM MRVL NXPI ON SWKS MPWR TER ENTG STX WDC HPQ HPE DELL IBM TYL PTC ANSS
    ROP GDDY VRSN AKAM FFIV JNPR CIEN COHR GLW APH TDY KEYS ZBRA TRMB EPAM CTSH INFY
""")
US_COMM = _rows("NASDAQ", "US", "Communication", """
    GOOGL GOOG META NFLX DIS CMCSA T VZ TMUS CHTR WBD PARA EA TTWO RBLX SPOT PINS
    SNAP MTCH LYV OMC IPG NWSA FOXA
""")
US_CONSUMER = _rows("NYSE", "US", "Consumer", """
    AMZN TSLA HD MCD NKE SBUX LOW TJX BKNG ABNB MAR HLT CMG ORLY AZO ROST DHI LEN
    NVR PHM GM F RIVN LULU DKS YUM DRI QSR EXPE UBER LYFT DASH ETSY EBAY W CVNA
    GRMN WHR NCLH RCL CCL WYNN LVS MGM
""")
US_STAPLES = _rows("NYSE", "US", "Staples", """
    PG KO PEP COST WMT TGT MDLZ CL KMB GIS K HSY SYY KR DG DLTR STZ MNST KDP CHD
    CLX MKC HRL CAG SJM TSN ADM BG PM MO
""")
US_HEALTH = _rows("NYSE", "US", "Healthcare", """
    UNH JNJ LLY ABBV MRK PFE TMO ABT DHR AMGN GILD BMY CVS CI ELV HUM MCK COR CAH
    ZTS SYK BSX MDT EW ISRG BDX BAX HOLX RMD DXCM IDXX A IQV CRL VRTX REGN BIIB
    MRNA ILMN INCY ALNY NBIX SRPT
""")
US_FIN = _rows("NYSE", "US", "Financials", """
    BRK-B JPM BAC WFC C GS MS SCHW BLK BX KKR APO ARES SPGI MCO MSCI ICE CME NDAQ
    CBOE AXP V MA PYPL FI FIS GPN COF DFS SYF USB PNC TFC MTB FITB HBAN RF KEY CFG
    ALL PGR TRV CB AIG MET PRU AFL HIG
""")
US_INDUSTRIAL = _rows("NYSE", "US", "Industrials", """
    CAT DE HON GE RTX LMT NOC GD LHX BA TDG HEI UNP CSX NSC ODFL JBHT CHRW UPS FDX
    ETN EMR PH ROK DOV ITW MMM CMI PCAR WM RSG URI FAST GWW PWR AME XYL IR SWK
    AXON LDOS
""")
US_ENERGY = _rows("NYSE", "US", "Energy", """
    XOM CVX COP EOG PXD OXY PSX VLO MPC SLB HAL BKR DVN FANG HES APA MRO CTRA EQT
    AR RRC OVV KMI WMB OKE TRGP LNG
""")
US_MATERIALS = _rows("NYSE", "US", "Materials", """
    LIN APD SHW ECL DD DOW LYB PPG NUE STLD X CLF FCX NEM AA MOS CF ALB VMC MLM
    IP PKG BALL AMCR
""")
US_UTILITIES = _rows("NYSE", "US", "Utilities", """
    NEE DUK SO D AEP EXC XEL SRE PEG ED WEC ES AEE CMS DTE PPL FE ETR CNP NRG VST
    CEG AES
""")
US_REIT = _rows("NYSE", "US", "Real Estate", """
    PLD AMT CCI EQIX DLR SPG O PSA WELL VTR AVB EQR MAA ESS UDR INVH SUI IRM WY
    ARE BXP KIM REG
""")

# ---------------------------------------------------------------------------------
# Nordics + Germany
# ---------------------------------------------------------------------------------
STOCKHOLM = _rows("STO", "SE", "Industrials", """
    ATCO-A.ST ATCO-B.ST VOLV-A.ST VOLV-B.ST SAND.ST SKF-B.ST ALFA.ST EPI-A.ST EPI-B.ST
    HEXA-B.ST ASSA-B.ST SECU-B.ST NIBE-B.ST TREL-B.ST INDU-C.ST ADDT-B.ST LIFCO-B.ST
    SAAB-B.ST BEIJ-B.ST INDT.ST
""") + _rows("STO", "SE", "Financials", """
    INVE-B.ST SEB-A.ST SWED-A.ST SHB-A.ST NDA-SE.ST EQT.ST LATO-B.ST KINV-B.ST
""") + _rows("STO", "SE", "Technology", """
    ERIC-B.ST EVO.ST SINCH.ST TIETO.ST
""") + _rows("STO", "SE", "Consumer", """
    HM-B.ST ESSITY-B.ST AZA.ST NIBE-B.ST ELUX-B.ST THULE.ST
""") + _rows("STO", "SE", "Materials", """
    BOL.ST SSAB-B.ST SCA-B.ST HOLM-B.ST
""") + _rows("STO", "SE", "Healthcare", """
    GETI-B.ST SWMA.ST ADDV-B.ST
""")

OSLO = _rows("OSL", "NO", "Energy", """
    EQNR.OL AKRBP.OL VAR.OL DNO.OL SUBC.OL TGS.OL BWLPG.OL FRO.OL GOGL.OL
""") + _rows("OSL", "NO", "Financials", "DNB.OL STB.OL GJF.OL") \
  + _rows("OSL", "NO", "Consumer", "MOWI.OL SALM.OL LSG.OL ORK.OL") \
  + _rows("OSL", "NO", "Materials", "YAR.OL NHY.OL BRG.OL") \
  + _rows("OSL", "NO", "Technology", "NOD.OL KOG.OL TEL.OL")

COPENHAGEN = _rows("CPH", "DK", "Healthcare", "NOVO-B.CO GN.CO DEMANT.CO ZEAL.CO ALKB.CO") \
  + _rows("CPH", "DK", "Industrials", "VWS.CO DSV.CO ROCK-B.CO FLS.CO NKT.CO TRMD-A.CO") \
  + _rows("CPH", "DK", "Financials", "DANSKE.CO TRYG.CO JYSK.CO SYDB.CO") \
  + _rows("CPH", "DK", "Consumer", "CARL-B.CO PNDORA.CO AMBU-B.CO COLO-B.CO ORSTED.CO")

HELSINKI = _rows("HEL", "FI", "Technology", "NOKIA.HE TIETO.HE QTCOM.HE") \
  + _rows("HEL", "FI", "Industrials", "KNEBV.HE WRT1V.HE VALMT.HE KESKOB.HE METSO.HE CGCBV.HE KCR.HE") \
  + _rows("HEL", "FI", "Materials", "UPM.HE STERV.HE OUT1V.HE HUH1V.HE") \
  + _rows("HEL", "FI", "Financials", "NDA-FI.HE SAMPO.HE") \
  + _rows("HEL", "FI", "Utilities", "FORTUM.HE") \
  + _rows("HEL", "FI", "Consumer", "ORNBV.HE NESTE.HE ELISA.HE")

FRANKFURT = _rows("FRA", "DE", "Technology", "SAP.DE IFX.DE SIE.DE") \
  + _rows("FRA", "DE", "Industrials", "AIR.DE MTX.DE RHM.DE HEI.DE SHL.DE DHL.DE BAS.DE") \
  + _rows("FRA", "DE", "Consumer", "VOW3.DE BMW.DE MBG.DE ADS.DE PUM.DE ZAL.DE HFG.DE CON.DE P911.DE") \
  + _rows("FRA", "DE", "Financials", "ALV.DE DBK.DE MUV2.DE DB1.DE CBK.DE HNR1.DE") \
  + _rows("FRA", "DE", "Healthcare", "BAYN.DE MRK.DE FRE.DE QIA.DE SRT3.DE") \
  + _rows("FRA", "DE", "Utilities", "RWE.DE EOAN.DE") \
  + _rows("FRA", "DE", "Communication", "DTE.DE 1COV.DE")

# ---------------------------------------------------------------------------------
# Rest of world equities
# ---------------------------------------------------------------------------------
TSX = _rows("TSX", "CA", "Financials", "RY.TO TD.TO BNS.TO BMO.TO CM.TO MFC.TO SLF.TO IFC.TO") \
  + _rows("TSX", "CA", "Energy", "ENB.TO TRP.TO CNQ.TO SU.TO IMO.TO CVE.TO PPL.TO TOU.TO") \
  + _rows("TSX", "CA", "Materials", "ABX.TO AEM.TO WPM.TO FNV.TO TECK-B.TO NTR.TO FM.TO") \
  + _rows("TSX", "CA", "Industrials", "CNR.TO CP.TO WCN.TO TFII.TO") \
  + _rows("TSX", "CA", "Technology", "SHOP.TO CSU.TO OTEX.TO GIB-A.TO")

LSE = _rows("LSE", "UK", "Energy", "SHEL.L BP.L") \
  + _rows("LSE", "UK", "Healthcare", "AZN.L GSK.L") \
  + _rows("LSE", "UK", "Financials", "HSBA.L BARC.L LLOY.L NWG.L PRU.L LGEN.L AV.L STAN.L") \
  + _rows("LSE", "UK", "Staples", "ULVR.L DGE.L BATS.L TSCO.L RKT.L") \
  + _rows("LSE", "UK", "Materials", "RIO.L GLEN.L AAL.L ANTO.L") \
  + _rows("LSE", "UK", "Industrials", "REL.L BA.L RR.L EXPN.L SGE.L")

ASX = _rows("ASX", "AU", "Materials", "BHP.AX RIO.AX FMG.AX NST.AX S32.AX PLS.AX MIN.AX") \
  + _rows("ASX", "AU", "Financials", "CBA.AX NAB.AX WBC.AX ANZ.AX MQG.AX QBE.AX SUN.AX") \
  + _rows("ASX", "AU", "Healthcare", "CSL.AX RMD.AX COH.AX SHL.AX") \
  + _rows("ASX", "AU", "Consumer", "WES.AX WOW.AX COL.AX ALL.AX JBH.AX") \
  + _rows("ASX", "AU", "Industrials", "TCL.AX QAN.AX BXB.AX")

NZX = _rows("NZX", "NZ", "Healthcare", "FPH.NZ EBO.NZ") \
  + _rows("NZX", "NZ", "Industrials", "AIR.NZ AIA.NZ POT.NZ") \
  + _rows("NZX", "NZ", "Utilities", "MCY.NZ MEL.NZ CEN.NZ GNE.NZ") \
  + _rows("NZX", "NZ", "Consumer", "FBU.NZ ATM.NZ SPK.NZ")

TOKYO = _rows("TSE", "JP", "Industrials", "7203.T 6501.T 6503.T 6301.T 7011.T 6902.T") \
  + _rows("TSE", "JP", "Technology", "6758.T 6857.T 8035.T 6954.T 6981.T 4063.T") \
  + _rows("TSE", "JP", "Financials", "8306.T 8316.T 8411.T 8766.T") \
  + _rows("TSE", "JP", "Consumer", "9983.T 7267.T 7974.T 4661.T")

HK = _rows("HKEX", "HK", "Technology", "0700.HK 9988.HK 3690.HK 1810.HK 9618.HK") \
  + _rows("HKEX", "HK", "Financials", "0005.HK 1299.HK 0388.HK 2318.HK") \
  + _rows("HKEX", "HK", "Energy", "0883.HK 0857.HK") \
  + _rows("HKEX", "HK", "Consumer", "2020.HK 0288.HK 1876.HK")

# ---------------------------------------------------------------------------------
# Bonds — treasury, credit, inflation, international, plus rate futures
# ---------------------------------------------------------------------------------
BONDS = _rows("NASDAQ", "US", "Rates", """
    SHY IEI IEF TLH TLT GOVT SCHO SCHR SPTL VGSH VGIT VGLT BIL SGOV TFLO STIP TIP
    SCHP VTIP
""", "bond") + _rows("NYSE", "US", "Credit", """
    LQD VCSH VCIT VCLT IGSB SPSB USIG HYG JNK SHYG SJNK ANGL FALN BKLN SRLN
""", "bond") + _rows("NYSE", "US", "Municipal", """
    MUB VTEB TFI SHM HYD SUB
""", "bond") + _rows("NYSE", "GLOBAL", "International", """
    BNDX BWX EMB VWOB PCY IGOV IBND EMLC
""", "bond") + _rows("NASDAQ", "US", "Aggregate", """
    AGG BND SCHZ SPAB FBND TOTL MBB VMBS
""", "bond")

BOND_FUTURES = _rows("GLOBEX", "US", "Rates", "ZT=F ZF=F ZN=F TN=F ZB=F UB=F GE=F SR3=F", "future")

# ---------------------------------------------------------------------------------
# FX — majors, minors, Nordic and exotic crosses
# ---------------------------------------------------------------------------------
FOREX = _rows("FOREX", "GLOBAL", "FX Majors", """
    EURUSD=X GBPUSD=X USDJPY=X USDCHF=X USDCAD=X AUDUSD=X NZDUSD=X
""", "forex") + _rows("FOREX", "GLOBAL", "FX Crosses", """
    EURGBP=X EURJPY=X EURCHF=X EURAUD=X EURCAD=X GBPJPY=X GBPCHF=X AUDJPY=X
    AUDNZD=X CADJPY=X CHFJPY=X NZDJPY=X
""", "forex") + _rows("FOREX", "GLOBAL", "FX Nordics", """
    USDSEK=X EURSEK=X SEKNOK=X USDNOK=X EURNOK=X USDDKK=X EURDKK=X GBPSEK=X
    NOKSEK=X JPYSEK=X CHFSEK=X
""", "forex") + _rows("FOREX", "GLOBAL", "FX Emerging", """
    USDMXN=X USDZAR=X USDTRY=X USDBRL=X USDINR=X USDCNY=X USDPLN=X USDHUF=X
    USDSGD=X USDHKD=X
""", "forex")

# ---------------------------------------------------------------------------------
# Futures — index, energy, metals, ags, currencies
# ---------------------------------------------------------------------------------
FUTURES = _rows("GLOBEX", "US", "Index Futures", """
    ES=F NQ=F YM=F RTY=F MES=F MNQ=F VX=F
""", "future") + _rows("GLOBEX", "US", "Energy Futures", """
    CL=F BZ=F NG=F RB=F HO=F
""", "future") + _rows("GLOBEX", "US", "Metals Futures", """
    GC=F SI=F HG=F PL=F PA=F MGC=F
""", "future") + _rows("GLOBEX", "US", "Agri Futures", """
    ZC=F ZS=F ZW=F ZM=F ZL=F KC=F CT=F SB=F CC=F LE=F HE=F
""", "future") + _rows("GLOBEX", "GLOBAL", "FX Futures", """
    6E=F 6J=F 6B=F 6A=F 6C=F 6S=F DX=F
""", "future") + BOND_FUTURES

CRYPTO = _rows("CRYPTO", "GLOBAL", "Crypto", """
    BTC-USD ETH-USD SOL-USD BNB-USD XRP-USD ADA-USD AVAX-USD LINK-USD DOT-USD
    MATIC-USD LTC-USD ATOM-USD UNI-USD AAVE-USD ARB-USD OP-USD
""", "crypto")


UNIVERSES: Dict[str, Universe] = {
    "US_LARGE": Universe("US_LARGE", "US Large Cap (NYSE)", "NYSE",
                         US_CONSUMER + US_STAPLES + US_HEALTH + US_FIN + US_INDUSTRIAL
                         + US_ENERGY + US_MATERIALS + US_UTILITIES + US_REIT),
    "US_TECH": Universe("US_TECH", "US Technology & Comms (Nasdaq)", "NASDAQ", US_TECH + US_COMM),
    "TSX": Universe("TSX", "Toronto", "TSX", TSX),
    "STOCKHOLM": Universe("STOCKHOLM", "Nasdaq Stockholm", "STO", STOCKHOLM),
    "OSLO": Universe("OSLO", "Oslo Bors", "OSL", OSLO),
    "COPENHAGEN": Universe("COPENHAGEN", "Nasdaq Copenhagen", "CPH", COPENHAGEN),
    "HELSINKI": Universe("HELSINKI", "Nasdaq Helsinki", "HEL", HELSINKI),
    "FRANKFURT": Universe("FRANKFURT", "Xetra Frankfurt", "FRA", FRANKFURT),
    "LSE": Universe("LSE", "London", "LSE", LSE),
    "ASX": Universe("ASX", "Australia", "ASX", ASX),
    "NZX": Universe("NZX", "New Zealand", "NZX", NZX),
    "TOKYO": Universe("TOKYO", "Tokyo", "TSE", TOKYO),
    "HONGKONG": Universe("HONGKONG", "Hong Kong", "HKEX", HK),
    "BONDS": Universe("BONDS", "Global Bonds", "NYSE", BONDS, asset_class="bond"),
    "FOREX": Universe("FOREX", "FX (24/5)", "FOREX", FOREX, asset_class="forex"),
    "FUTURES": Universe("FUTURES", "Futures (23/5)", "GLOBEX", FUTURES, asset_class="future"),
    "CRYPTO": Universe("CRYPTO", "Crypto Majors", "CRYPTO", CRYPTO, asset_class="crypto"),
}


def get_universe(key: str) -> Universe:
    if key not in UNIVERSES:
        raise KeyError(f"Unknown universe '{key}'. Known: {sorted(UNIVERSES)}")
    return UNIVERSES[key]


def universes_for_exchanges(codes: List[str]) -> List[Universe]:
    return [u for u in UNIVERSES.values() if u.exchange in codes]


def find_symbol(ticker: str) -> Optional[Symbol]:
    for universe in UNIVERSES.values():
        for symbol in universe.symbols:
            if symbol.ticker == ticker:
                return symbol
    return None


def symbol_count() -> int:
    return sum(len(u.symbols) for u in UNIVERSES.values())
