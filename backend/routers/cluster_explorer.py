"""Market Cluster Explorer API router."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from analytics.features.registry import get_registry
from analytics.models.clustering_result import AnalyzeRequest
from analytics.models.universe import UniverseCreate
from analytics.services.universe_service import UniverseService
from analytics.services.data_quality_service import DataQualityService
from analytics.services.clustering_service import ClusteringService
from analytics.services.coverage_service import CoverageService
from analytics.services.dataset_service import DatasetService
from analytics.services.export_service import ExportService
from analytics.data.market_data_provider import MarketDataProvider
from analytics.utils.json_safe import sanitize_for_json

router = APIRouter(prefix="/api/cluster", tags=["cluster-explorer"])

_CUSTOM_PROFILES: dict[str, dict] = {}


class CustomProfileCreate(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    features: list[str]


@router.get("/inspect")
def inspect_project(db: Session = Depends(get_db)):
    registry = get_registry()
    universes = UniverseService(db).list_universes()
    from models import Stock, StockFeature
    stock_count = db.query(Stock).count()
    feature_count = db.query(StockFeature).count()
    return {
        "project": "stock-portfolio-unifier",
        "module": "Market Cluster Explorer",
        "version": "2.0",
        "stocks_in_db": stock_count,
        "features_in_db": feature_count,
        "discovered_variables": len(registry.features),
        "universes": len(universes),
        "profiles": [p.name for p in registry.list_profiles()],
        "custom_profiles": list(_CUSTOM_PROFILES.keys()),
    }


@router.get("/features")
def list_features():
    return get_registry().to_dict()


@router.get("/universes")
def list_universes(db: Session = Depends(get_db)):
    svc = UniverseService(db)
    return [u.model_dump() for u in svc.list_universes()]


@router.post("/universes", status_code=201)
def create_universe(data: UniverseCreate, db: Session = Depends(get_db)):
    u = UniverseService(db).create_universe(data)
    return u.model_dump()


@router.get("/coverage")
def get_coverage(
    universe_id: str = Query("dow30"),
    period_days: int = Query(365),
    feature_profile: str = Query("ALL_CLUSTERING_ELIGIBLE_FEATURES"),
    features: str = Query("", description="Comma-separated feature override"),
    db: Session = Depends(get_db),
):
    selected = [f.strip() for f in features.split(",") if f.strip()] or None
    return sanitize_for_json(
        CoverageService(db).get_coverage(universe_id, period_days, feature_profile, selected)
    )


@router.get("/dataset")
def get_dataset(
    universe_id: str = Query("dow30"),
    view: str = Query("raw"),
    period_days: int = Query(365),
    feature_profile: str = Query("ALL_CLUSTERING_ELIGIBLE_FEATURES"),
    features: str = Query(""),
    db: Session = Depends(get_db),
):
    selected = [f.strip() for f in features.split(",") if f.strip()] or None
    return sanitize_for_json(
        DatasetService(db).get_dataset(universe_id, view, period_days, feature_profile, selected)
    )


@router.post("/profiles/custom", status_code=201)
def create_custom_profile(data: CustomProfileCreate):
    _CUSTOM_PROFILES[data.name] = data.model_dump()
    return data.model_dump()


@router.get("/profiles/custom")
def list_custom_profiles():
    return list(_CUSTOM_PROFILES.values())


@router.post("/validate")
def validate_data(
    universe_id: str = Query("dow30"),
    tickers: str = Query("", description="Comma-separated tickers override"),
    period_days: int = Query(365),
    db: Session = Depends(get_db),
):
    usvc = UniverseService(db)
    ticker_list = usvc.resolve_tickers(
        universe_id,
        [t.strip() for t in tickers.split(",") if t.strip()] or None,
    )
    report, df = DataQualityService(db).validate_universe(ticker_list, period_days, universe_id)
    return sanitize_for_json({
        "report": report.model_dump(),
        "assets_found": len(df),
        "columns": list(df.columns),
    })


@router.post("/refresh-missing")
def refresh_missing(
    universe_id: str = Query("dow30"),
    db: Session = Depends(get_db),
):
    usvc = UniverseService(db)
    tickers = usvc.resolve_tickers(universe_id)
    return MarketDataProvider(db).refresh_missing(tickers)


@router.post("/analyze")
def analyze(request: AnalyzeRequest, db: Session = Depends(get_db)):
    usvc = UniverseService(db)
    tickers = usvc.resolve_tickers(request.universe_id, request.tickers)
    if not tickers:
        raise HTTPException(400, "No tickers in universe")
    try:
        result = ClusteringService(db).analyze(request, tickers)
        return sanitize_for_json(result.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/runs")
def list_runs(limit: int = Query(20), db: Session = Depends(get_db)):
    return sanitize_for_json(ClusteringService(db).list_runs(limit))


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    cs = ClusteringService(db)
    result = cs.get_run(run_id)
    if not result:
        raise HTTPException(404, "Run not found")
    return sanitize_for_json({
        "result": result.model_dump(),
        "charts": cs.get_run_data(run_id),
    })


@router.get("/dataset/export")
def export_dataset(
    universe_id: str = Query("dow30"),
    view: str = Query("raw"),
    format: str = Query("csv"),
    period_days: int = Query(365),
    feature_profile: str = Query("ALL_CLUSTERING_ELIGIBLE_FEATURES"),
    features: str = Query(""),
    db: Session = Depends(get_db),
):
    selected = [f.strip() for f in features.split(",") if f.strip()] or None
    exp = ExportService(ClusteringService(db), db)
    try:
        content, filename = exp.export_dataset(universe_id, view, format, period_days, feature_profile, selected)
        mime = {
            "csv": "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "parquet": "application/octet-stream",
        }.get(format, "application/octet-stream")
        return Response(content, media_type=mime,
                        headers={"Content-Disposition": f"attachment; filename={filename}"})
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/runs/{run_id}/export/validate")
def validate_notebook_export(run_id: str, db: Session = Depends(get_db)):
    exp = ExportService(ClusteringService(db), db)
    try:
        errors = exp.validate_notebook_cells(run_id)
        return {"valid": len(errors) == 0, "errors": errors}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/runs/{run_id}/export")
def export_run(
    run_id: str,
    format: str = Query("csv"),
    db: Session = Depends(get_db),
):
    cs = ClusteringService(db)
    exp = ExportService(cs, db)
    try:
        if format == "csv":
            content = exp.export_csv(run_id)
            return Response(content, media_type="text/csv",
                            headers={"Content-Disposition": f"attachment; filename=clusters_{run_id}.csv"})
        if format == "xlsx":
            content = exp.export_excel(run_id)
            return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename=market_cluster_{run_id}.xlsx"})
        if format == "json":
            content = exp.export_json(run_id)
            return Response(content, media_type="application/json",
                            headers={"Content-Disposition": f"attachment; filename=results_{run_id}.json"})
        if format == "parquet":
            content = exp.export_parquet_features(run_id)
            return Response(content, media_type="application/octet-stream",
                            headers={"Content-Disposition": f"attachment; filename=features_{run_id}.parquet"})
        if format == "ipynb":
            content = exp.export_notebook(run_id)
            return Response(content, media_type="application/x-ipynb+json",
                            headers={"Content-Disposition": f"attachment; filename=analysis_{run_id}.ipynb"})
        if format == "bundle":
            content, status = exp.export_full_bundle(run_id)
            return Response(content, media_type="application/zip",
                            headers={
                                "Content-Disposition": f"attachment; filename=market_cluster_{run_id}.zip",
                                "X-Export-Status": status.get("notebook_executed", "unknown"),
                            })
        content = exp.export_zip_bundle(run_id)
        return Response(content, media_type="application/zip",
                        headers={"Content-Disposition": f"attachment; filename=cluster_run_{run_id}.zip"})
    except ValueError as e:
        raise HTTPException(404, str(e))
