"""
🔧 Water Analysis Tool — AquaGuard Agent
Core Python tool for water quality analysis, potability prediction,
and dataset operations. Used by all agents via tool invocation.
"""

import os
import pickle
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATASET_SLUG = "adityakadiwal/water-potability"

SAFE_RANGES = {
    "ph":               (6.5, 8.5),
    "Hardness":         (0, 300),
    "Solids":           (0, 500),
    "Chloramines":      (0, 4),
    "Sulfate":          (0, 250),
    "Conductivity":     (0, 400),
    "Organic_carbon":   (0, 2),
    "Trihalomethanes":  (0, 80),
    "Turbidity":        (0, 5),
}

DISEASE_RISK_MAP = {
    "ph":              "Gastrointestinal irritation, metal leaching from pipes",
    "Hardness":        "Kidney stones, cardiovascular issues (very high levels)",
    "Solids":          "Heavy metal poisoning, laxative effects",
    "Chloramines":     "Respiratory irritation, bladder cancer risk (prolonged)",
    "Sulfate":         "Diarrhea, dehydration (especially in children)",
    "Conductivity":    "Indicator of high ionic contamination",
    "Organic_carbon":  "Disinfection by-product formation, liver/kidney damage",
    "Trihalomethanes": "Cancer risk (bladder, colon), reproductive issues",
    "Turbidity":       "Pathogen harboring — cholera, dysentery, typhoid",
}

TREATMENT_METHODS = {
    "ph": {
        "low":  ["Add limestone or soda ash to raise pH", "Install a calcite neutralizer filter"],
        "high": ["Add white vinegar or citric acid", "Install an acid injection system"],
    },
    "Hardness": {
        "high": ["Install a water softener (ion exchange)", "Use reverse osmosis (RO) for drinking water"],
    },
    "Solids": {
        "high": ["Install a reverse osmosis (RO) system", "Use distillation", "Blend with rainwater"],
    },
    "Chloramines": {
        "high": ["Use a catalytic carbon filter", "Install whole-house activated carbon system"],
    },
    "Sulfate": {
        "high": ["Use reverse osmosis filtration", "Install ion-exchange treatment unit"],
    },
    "Conductivity": {
        "high": ["Use RO or deionization filters", "Investigate contamination source"],
    },
    "Organic_carbon": {
        "high": ["Use activated carbon filtration", "Apply UV disinfection", "Protect from agricultural runoff"],
    },
    "Trihalomethanes": {
        "high": ["Install activated carbon filter", "Aerate water to volatilize THMs"],
    },
    "Turbidity": {
        "high": ["Use multi-stage sediment filter", "Boil for 1+ minute", "Apply coagulation with alum"],
    },
}


# ---------------------------------------------------------------------------
# Dataset Operations
# ---------------------------------------------------------------------------
def load_dataset(dataset_path: str = "") -> dict:
    """
    Load the water potability dataset from a local CSV path or download
    from Kaggle via kagglehub.

    Args:
        dataset_path: Optional local path to the CSV file. If empty,
                      attempts to download from Kaggle.

    Returns:
        dict with status, row count, columns, missing value info, and sample rows.
    """
    try:
        if dataset_path and os.path.exists(dataset_path):
            csv_path = dataset_path
        else:
            import kagglehub
            download_dir = kagglehub.dataset_download(DATASET_SLUG)
            csv_path = os.path.join(download_dir, "water_potability.csv")

        df = pd.read_csv(csv_path)
        missing = {k: int(v) for k, v in df.isnull().sum().items() if v > 0}

        return {
            "status": "success",
            "rows": len(df),
            "columns": list(df.columns),
            "missing": missing,
            "sample": df.head().to_dict(orient="records"),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def preprocess_data(dataset_path: str = "") -> dict:
    """
    Preprocess the dataset: median imputation for missing values,
    IQR-based outlier detection, and summary statistics.

    Args:
        dataset_path: Optional local path to the CSV file.

    Returns:
        dict with preprocessing results including imputed columns,
        outlier counts, and summary statistics.
    """
    try:
        if dataset_path and os.path.exists(dataset_path):
            csv_path = dataset_path
        else:
            import kagglehub
            download_dir = kagglehub.dataset_download(DATASET_SLUG)
            csv_path = os.path.join(download_dir, "water_potability.csv")

        df = pd.read_csv(csv_path)

        # Median imputation
        imputed_columns = []
        for col in df.columns:
            if df[col].isnull().any():
                df[col] = df[col].fillna(df[col].median())
                imputed_columns.append(col)

        # IQR outlier detection
        outlier_counts = {}
        for col in SAFE_RANGES:
            if col in df.columns:
                q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
                iqr = q3 - q1
                n_outliers = int(((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum())
                if n_outliers > 0:
                    outlier_counts[col] = n_outliers

        summary = {
            col: {stat: round(float(val), 4) for stat, val in stats.items()}
            for col, stats in df.describe().to_dict().items()
        }

        return {
            "status": "success",
            "rows": len(df),
            "imputed_columns": imputed_columns,
            "outlier_counts": outlier_counts,
            "summary_stats": summary,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Input Sanitization & Validation (Security Feature)
# ---------------------------------------------------------------------------
def sanitize_inputs(params: dict) -> tuple[dict, str]:
    """
    Sanitize and validate water parameters to prevent injection or invalid processing.
    
    Returns:
        tuple (sanitized_dict, error_message)
    """
    sanitized = {}
    errors = []
    
    key_mapping = {
        "ph": "ph",
        "hardness": "Hardness",
        "solids": "Solids",
        "chloramines": "Chloramines",
        "sulfate": "Sulfate",
        "conductivity": "Conductivity",
        "organic_carbon": "Organic_carbon",
        "trihalomethanes": "Trihalomethanes",
        "turbidity": "Turbidity"
    }

    for k, v in params.items():
        if v is None or v == "":
            continue
        
        try:
            val = float(v)
        except (ValueError, TypeError):
            errors.append(f"Invalid value for '{k}': must be a valid number.")
            continue

        clean_key = key_mapping.get(k.lower(), k)
        
        # Physical bounds checking
        if clean_key == "ph":
            if val < 0.0 or val > 14.0:
                errors.append(f"pH value ({val}) is out of physical bounds (0.0 to 14.0).")
            else:
                sanitized[clean_key] = val
        else:
            if val < 0.0:
                errors.append(f"Parameter '{clean_key}' value ({val}) cannot be negative.")
            else:
                sanitized[clean_key] = val

    err_msg = "; ".join(errors) if errors else ""
    return sanitized, err_msg


# ---------------------------------------------------------------------------
# Water Sample Validation
# ---------------------------------------------------------------------------
def validate_water_sample(
    ph: float = None,
    hardness: float = None,
    solids: float = None,
    chloramines: float = None,
    sulfate: float = None,
    conductivity: float = None,
    organic_carbon: float = None,
    trihalomethanes: float = None,
    turbidity: float = None,
) -> dict:
    """
    Validate a user-submitted water sample against WHO safe ranges.

    Returns:
        dict with provided parameters, violations, and an all_safe flag.
    """
    raw_params = {
        "ph": ph, "hardness": hardness, "solids": solids,
        "chloramines": chloramines, "sulfate": sulfate,
        "conductivity": conductivity, "organic_carbon": organic_carbon,
        "trihalomethanes": trihalomethanes, "turbidity": turbidity,
    }
    provided, err_msg = sanitize_inputs(raw_params)
    if err_msg:
        return {"status": "error", "message": f"Input validation failed: {err_msg}"}

    violations = []

    for param, value in provided.items():
        if param in SAFE_RANGES:
            lo, hi = SAFE_RANGES[param]
            if value < lo or value > hi:
                violations.append({
                    "parameter": param,
                    "value": value,
                    "safe_min": lo,
                    "safe_max": hi,
                    "severity": "HIGH" if abs(value - hi) > hi * 0.5 else "MODERATE",
                })

    return {
        "status": "success",
        "provided_params": provided,
        "violations": violations,
        "all_safe": len(violations) == 0,
    }


# ---------------------------------------------------------------------------
# Machine Learning Model & Training (Kaggle Dataset)
# ---------------------------------------------------------------------------

MODEL_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "potability_model.pkl")
_LOADED_MODEL = None

def train_and_save_model(dataset_path: str = "") -> dict:
    """
    Train a Random Forest Classifier on the preprocessed Kaggle water potability dataset.
    Saves the trained model, feature medians (for imputation), and test metrics to disk.
    """
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, precision_score, recall_score
        
        # Load dataset
        if dataset_path and os.path.exists(dataset_path):
            csv_path = dataset_path
        else:
            import kagglehub
            download_dir = kagglehub.dataset_download(DATASET_SLUG)
            csv_path = os.path.join(download_dir, "water_potability.csv")

        df = pd.read_csv(csv_path)

        # Impute missing values and save medians for future validation/prediction imputation
        medians = {}
        features = [
            "ph", "Hardness", "Solids", "Chloramines", "Sulfate",
            "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity"
        ]
        
        for col in features:
            median_val = df[col].median()
            medians[col] = float(median_val)
            df[col] = df[col].fillna(median_val)

        X = df[features]
        y = df["Potability"]

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Train model
        model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=12)
        model.fit(X_train, y_train)

        # Evaluate model
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)

        # Ensure the data directory exists
        os.makedirs(os.path.dirname(MODEL_FILE), exist_ok=True)

        # Save model pack
        model_pack = {
            "model": model,
            "medians": medians,
            "metrics": {
                "accuracy": float(accuracy),
                "precision": float(precision),
                "recall": float(recall)
            }
        }
        with open(MODEL_FILE, "wb") as f:
            pickle.dump(model_pack, f)

        global _LOADED_MODEL
        _LOADED_MODEL = None

        return {
            "status": "success",
            "metrics": model_pack["metrics"],
            "message": "Model trained and saved successfully."
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _predict_potability_fallback(provided: dict) -> dict:
    """Fallback rule-based prediction when ML model is not available."""
    violations = []
    param_scores = {}
    total_score = 0
    count = 0

    for param, value in provided.items():
        if param not in SAFE_RANGES:
            continue
        lo, hi = SAFE_RANGES[param]
        count += 1

        if lo <= value <= hi:
            mid = (lo + hi) / 2
            deviation = abs(value - mid) / (hi - lo) if (hi - lo) > 0 else 0
            score = max(0, 100 - deviation * 100)
            param_scores[param] = {"value": value, "score": round(score, 1), "status": "SAFE"}
        else:
            deviation = (abs(value - hi) / hi) if value > hi and hi > 0 else (abs(lo - value) / max(lo, 1))
            score = max(0, 100 - deviation * 150)
            severity = "HIGH" if deviation > 0.5 else "MODERATE"
            param_scores[param] = {"value": value, "score": round(score, 1), "status": severity}
            violations.append({
                "parameter": param, "value": value,
                "safe_range": f"{lo} – {hi}", "severity": severity,
            })

        total_score += score

    safety_score = round(total_score / count, 1) if count > 0 else 0
    potability = "SAFE" if safety_score >= 80 and not violations else "CAUTION" if safety_score >= 50 or len(violations) <= 1 else "UNSAFE"
    confidence = round(min(1.0, count / len(SAFE_RANGES)), 2)

    return {
        "status": "success",
        "potability": potability,
        "confidence": confidence,
        "safety_score": safety_score,
        "violations": violations,
        "parameter_scores": param_scores,
        "parameters_evaluated": count,
        "parameters_total": len(SAFE_RANGES),
        "using_ml_model": False
    }


# ---------------------------------------------------------------------------
# Potability Prediction
# ---------------------------------------------------------------------------
def predict_potability(
    ph: float = None,
    hardness: float = None,
    solids: float = None,
    chloramines: float = None,
    sulfate: float = None,
    conductivity: float = None,
    organic_carbon: float = None,
    trihalomethanes: float = None,
    turbidity: float = None,
) -> dict:
    """
    Predict water potability using a trained Random Forest model.
    Falls back to a rule-based WHO threshold check if the model isn't trained.

    Returns:
        dict with potability classification, safety score, confidence,
        violations, and per-parameter scores.
    """
    raw_params = {
        "ph": ph, "hardness": hardness, "solids": solids,
        "chloramines": chloramines, "sulfate": sulfate,
        "conductivity": conductivity, "organic_carbon": organic_carbon,
        "trihalomethanes": trihalomethanes, "turbidity": turbidity,
    }
    provided, err_msg = sanitize_inputs(raw_params)
    if err_msg:
        return {"status": "error", "message": f"Input validation failed: {err_msg}"}

    # Automatically train model if not present
    if not os.path.exists(MODEL_FILE):
        train_res = train_and_save_model()
        if train_res.get("status") == "error":
            return _predict_potability_fallback(provided)

    global _LOADED_MODEL
    try:
        if _LOADED_MODEL is None:
            with open(MODEL_FILE, "rb") as f:
                _LOADED_MODEL = pickle.load(f)
        
        model_pack = _LOADED_MODEL
        model = model_pack["model"]
        medians = model_pack["medians"]

        features = [
            "ph", "Hardness", "Solids", "Chloramines", "Sulfate",
            "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity"
        ]
        
        input_data = []
        for feature in features:
            val = provided.get(feature)
            if val is None:
                # Impute missing parameters using medians from training
                val = medians.get(feature, 0.0)
            input_data.append(val)

        # Predict probability of potability (class 1)
        prob = model.predict_proba([input_data])[0][1]
        potability_class = int(model.predict([input_data])[0])

        safety_score = round(prob * 100, 1)

        # Identify safe range violations (WHO standards) for explainability
        violations = []
        param_scores = {}
        for param in features:
            value = provided.get(param)
            if value is not None:
                lo, hi = SAFE_RANGES[param]
                if value < lo or value > hi:
                    severity = "HIGH" if (value > hi and (value - hi) > hi * 0.5) or (value < lo and (lo - value) > lo * 0.5) else "MODERATE"
                    violations.append({
                        "parameter": param, "value": value,
                        "safe_range": f"{lo} – {hi}", "severity": severity,
                    })
                    param_scores[param] = {"value": value, "status": severity}
                else:
                    param_scores[param] = {"value": value, "status": "SAFE"}

        # Determine overall potability status classification
        if potability_class == 1 and prob >= 0.60:
            potability = "SAFE"
        elif prob >= 0.35:
            potability = "CAUTION"
        else:
            potability = "UNSAFE"

        confidence = round(prob if potability_class == 1 else (1.0 - prob), 2)

        return {
            "status": "success",
            "potability": potability,
            "confidence": confidence,
            "safety_score": safety_score,
            "violations": violations,
            "parameter_scores": param_scores,
            "parameters_evaluated": len(provided),
            "parameters_total": len(SAFE_RANGES),
            "using_ml_model": True,
            "model_metrics": model_pack["metrics"]
        }

    except Exception:
        return _predict_potability_fallback(provided)


# ---------------------------------------------------------------------------
# Disease Risk Assessment
# ---------------------------------------------------------------------------
def assess_disease_risk(
    ph: float = None,
    hardness: float = None,
    solids: float = None,
    chloramines: float = None,
    sulfate: float = None,
    conductivity: float = None,
    organic_carbon: float = None,
    trihalomethanes: float = None,
    turbidity: float = None,
) -> dict:
    """
    Assess disease risk by mapping out-of-range water parameters to
    associated health threats.

    Returns:
        dict with overall risk level, risk score, identified risks,
        and vulnerable populations.
    """
    raw_params = {
        "ph": ph, "hardness": hardness, "solids": solids,
        "chloramines": chloramines, "sulfate": sulfate,
        "conductivity": conductivity, "organic_carbon": organic_carbon,
        "trihalomethanes": trihalomethanes, "turbidity": turbidity,
    }
    provided, err_msg = sanitize_inputs(raw_params)
    if err_msg:
        return {"status": "error", "message": f"Input validation failed: {err_msg}"}

    if not provided:
        return {"status": "error", "message": "No parameters provided."}

    identified_risks = []
    risk_points = 0

    for param, value in provided.items():
        if param not in SAFE_RANGES:
            continue
        lo, hi = SAFE_RANGES[param]
        if value < lo or value > hi:
            deviation = abs(value - hi) / hi if value > hi and hi > 0 else abs(lo - value) / max(lo, 1)
            severity_points = min(30, deviation * 20)
            risk_points += severity_points
            identified_risks.append({
                "parameter": param, "value": value,
                "safe_range": f"{lo} – {hi}",
                "associated_diseases": DISEASE_RISK_MAP.get(param, "Unknown"),
                "severity_contribution": round(severity_points, 1),
            })

    risk_score = min(100, round(risk_points, 1))
    overall_risk = "CRITICAL" if risk_score >= 70 else "HIGH" if risk_score >= 45 else "MODERATE" if risk_score >= 20 else "LOW"

    vulnerable_groups = []
    if risk_score > 20:
        vulnerable_groups = ["Infants and young children", "Pregnant women", "Elderly individuals", "Immunocompromised persons"]
    if risk_score > 50:
        vulnerable_groups.append("General population with prolonged exposure")

    return {
        "status": "success",
        "overall_risk": overall_risk,
        "risk_score": risk_score,
        "identified_risks": identified_risks,
        "vulnerable_groups": vulnerable_groups,
    }


# ---------------------------------------------------------------------------
# Treatment Recommendations
# ---------------------------------------------------------------------------
def get_treatment_recommendations(
    ph: float = None,
    hardness: float = None,
    solids: float = None,
    chloramines: float = None,
    sulfate: float = None,
    conductivity: float = None,
    organic_carbon: float = None,
    trihalomethanes: float = None,
    turbidity: float = None,
) -> dict:
    """
    Generate treatment recommendations for out-of-range water parameters.

    Returns:
        dict with treatment methods per violation, priority ranking,
        and general tips.
    """
    raw_params = {
        "ph": ph, "hardness": hardness, "solids": solids,
        "chloramines": chloramines, "sulfate": sulfate,
        "conductivity": conductivity, "organic_carbon": organic_carbon,
        "trihalomethanes": trihalomethanes, "turbidity": turbidity,
    }
    provided, err_msg = sanitize_inputs(raw_params)
    if err_msg:
        return {"status": "error", "message": f"Input validation failed: {err_msg}"}

    recommendations = []
    immediate_actions = []

    for param, value in provided.items():
        if param not in SAFE_RANGES:
            continue
        lo, hi = SAFE_RANGES[param]
        if lo <= value <= hi:
            continue

        direction = "low" if value < lo else "high"
        methods = TREATMENT_METHODS.get(param, {}).get(direction, [])
        deviation = abs(value - hi) / hi if value > hi and hi > 0 else abs(lo - value) / max(lo, 1)
        priority = "URGENT" if deviation > 0.5 else "RECOMMENDED"

        recommendations.append({
            "parameter": param, "current_value": value,
            "safe_range": f"{lo} – {hi}", "direction": f"Too {direction}",
            "priority": priority, "treatment_methods": methods,
        })

        if priority == "URGENT":
            immediate_actions.append(
                f"⚠️ {param} is critically {direction} ({value}). Do NOT consume without treatment."
            )

    if not recommendations:
        return {
            "status": "all_safe",
            "message": "All parameters are within safe ranges. No treatment needed!",
            "general_tips": [
                "Continue regular water testing (monthly recommended)",
                "Store water in clean, covered containers",
                "Clean water storage tanks every 6 months",
            ],
        }

    return {
        "status": "treatment_needed",
        "immediate_actions": immediate_actions,
        "recommendations": recommendations,
        "general_tips": [
            "Always boil water if unsure about safety",
            "Report water quality issues to local authorities",
            "Install point-of-use filters for drinking water",
        ],
    }


# ---------------------------------------------------------------------------
# Community Report Generation
# ---------------------------------------------------------------------------
def generate_community_report(
    location_name: str = "Your Area",
    risk_level: str = "MODERATE",
    violations: list = None,
    language: str = "English",
) -> dict:
    """
    Generate a community-friendly water quality alert report.

    Returns:
        dict with formatted report title, alert level, issues,
        key messages, and distribution notes.
    """
    if violations is None:
        violations = []

    risk_emoji = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
    emoji = risk_emoji.get(risk_level.upper(), "🟡")

    issue_lines = []
    for v in violations:
        param = v.get("parameter", "Unknown")
        value = v.get("value", "?")
        safe = v.get("safe_range", "?")
        issue_lines.append(f"• {param}: {value} (safe range: {safe})")

    issues_text = "\n".join(issue_lines) if issue_lines else "• No critical issues found"

    key_messages_map = {
        "LOW":      ["✅ Water is generally safe", "💡 Continue testing monthly"],
        "MODERATE": ["⚠️ Some issues detected", "🫗 Boil water before drinking", "👶 Use treated water for children"],
        "HIGH":     ["🚫 Do NOT drink without treatment", "🫗 Boil for 1+ minute", "🏥 Seek medical help if unwell", "📢 Share this alert"],
        "CRITICAL": ["🚨 EMERGENCY: Water unsafe for ALL uses", "🚰 Use only bottled/tanker water", "🏥 Visit health center if exposed", "📞 Contact water authority NOW"],
    }

    return {
        "title": f"💧 Water Quality Alert — {location_name}",
        "alert_level": f"{emoji} {risk_level.upper()}",
        "summary": f"Water quality analysis for {location_name} shows {risk_level.upper()} risk.",
        "issues_found": issues_text,
        "key_messages": key_messages_map.get(risk_level.upper(), key_messages_map["MODERATE"]),
        "language_note": f"Report prepared in {language}.",
    }
