import io
from datetime import datetime, timezone
from typing import NamedTuple
import piexif
from PIL import Image 
from app.core.logging import get_logger 
logger=get_logger(__name__)

class ExifData(NamedTuple):
    latitude: float | None
    longitude: float | None
    captured_at: datetime | None

def _dms_to_decimal(dms: tuple, ref: str) -> float:
    """Convert GPS (degrees-minutes-seconds) tuple to decimal degrees."""

    degrees = dms[0][0] / dms[0][1]
    minutes = dms[1][0] / dms[1][1] / 60
    seconds = dms[2][0] / dms[2][1] / 3600

    result=degrees+minutes+seconds
    if ref in ("S","W"):
        result=-result
    return round(result,7)

def extract_exif(image_bytes: bytes) -> ExifData:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        raw_exif = img.info.get("exif")
        if not raw_exif:
            return ExifData(None, None, None)
        exif_dict=piexif.load(raw_exif)
    except Exception as exc:
        logger.warning("exif_load_failed", error=str(exc))
        return ExifData(None, None, None)
    
    latitude=longitude=None
    gps=exif_dict.get("GPS", {})
    try:
        if piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps:
            lat_ref=gps[piexif.GPSIFD.GPSLatitudeRef].decode()
            lon_ref=gps[piexif.GPSIFD.GPSLongitudeRef].decode()
            latitude=_dms_to_decimal(gps[piexif.GPSIFD.GPSLatitude], lat_ref)
            longitude=_dms_to_decimal(gps[piexif.GPSIFD.GPSLongitude], lon_ref)
    except Exception as exc:
        logger.warning("exif_gps_parse_failed", error=str(exc))
        
    captured_at=None
    exif_0=exif_dict.get("Exif",{})
    try:
        raw_dt=exif_0.get(piexif.ExifIFD.DateTimeOriginal)
        if raw_dt:
            dt_str=raw_dt.decode().strip()
            captured_at=datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception as exc:
        logger.warning("exif_timestamp_parse_failed", error=str(exc))
    return ExifData(latitude=latitude, longitude=longitude, captured_at=captured_at)