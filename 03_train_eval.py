"""Paso 3: entrena y evalúa Config "optical" (Sentinel-2) vs Config "fusion" (Sentinel-2 + Sentinel-1).

    python 03_train_eval.py --epochs 15 --seeds 3

- Misma arquitectura (ResNet-18), mismo split por zona y mismas semillas en ambas configuraciones.
- Época y umbral se eligen SOLO con validación; las métricas finales se calculan en test.
- Prueba de oclusión: en test se tapa con "nube" sintética una región del canal óptico (igual para
  ambas configuraciones) para medir la robustez que aporta el radar.
- Reporta media ± desv. entre semillas, la diferencia pareada fusion - optical y el veredicto
  contra los criterios del documento.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from torch.utils.data import DataLoader, TensorDataset

import config as C
from models import build_model

DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ----------------------------------------------------------------- datos
def load(data_dir):
    X = np.load(Path(data_dir) / "X.npy", mmap_mode="r")
    y = np.load(Path(data_dir) / "Y.npy")[:, 0].astype(np.float32)
    meta = pd.read_csv(Path(data_dir) / "meta.csv", dtype={"tile": str})
    return X, y, meta


def make_groups(meta):
    """Grupos para evitar fuga espacial. Con pocos tiles se usan bloques espaciales de 512 px."""
    if meta["tile"].nunique() >= 10:
        return meta["tile"].values
    print("[aviso] pocos tiles: se agrupa por bloques espaciales de 512 px dentro de cada tile")
    return (meta["tile"] + "_" + (meta["row"] // 512).astype(str) + "_" + (meta["col"] // 512).astype(str)).values


def split_by_group(groups, seed):
    idx = np.arange(len(groups))
    tr, rest = next(GroupShuffleSplit(1, test_size=0.30, random_state=seed).split(idx, groups=groups))
    va_rel, te_rel = next(GroupShuffleSplit(1, test_size=0.50, random_state=seed)
                          .split(rest, groups=groups[rest]))
    return tr, rest[va_rel], rest[te_rel]


def channel_stats(X, idx, ch):
    n, s, s2 = 0, np.zeros(len(ch)), np.zeros(len(ch))
    for i in range(0, len(idx), 2048):
        a = np.asarray(X[np.sort(idx[i:i + 2048])])[:, ch].astype(np.float64)
        s += a.sum((0, 2, 3)); s2 += (a ** 2).sum((0, 2, 3)); n += a.shape[0] * a.shape[2] * a.shape[3]
    mean = s / n
    std = np.sqrt(np.maximum(s2 / n - mean ** 2, 0)) + 1e-6
    return mean.astype(np.float32).reshape(1, -1, 1, 1), std.astype(np.float32).reshape(1, -1, 1, 1)


def prep(X, idx, ch, mean, std):
    out = np.empty((len(idx), len(ch), X.shape[2], X.shape[3]), np.float16)
    for i in range(0, len(idx), 2048):
        b = idx[i:i + 2048]
        out[i:i + len(b)] = ((np.asarray(X[b])[:, ch].astype(np.float32) - mean) / std).astype(np.float16)
    return torch.from_numpy(out)


def occlusion_masks(n, P, seed):
    """Mitad de los parches con una 'nube' rectangular (50-100% de cada lado)."""
    rng = np.random.default_rng(seed)
    m = np.zeros((n, P, P), bool)
    for i in range(n):
        if rng.random() < 0.5:
            h, w = int(rng.integers(P // 2, P + 1)), int(rng.integers(P // 2, P + 1))
            r, c = int(rng.integers(0, P - h + 1)), int(rng.integers(0, P - w + 1))
            m[i, r:r + h, c:c + w] = True
    return torch.from_numpy(m)


# ----------------------------------------------------------------- métricas
def threshold_max_f1(y, p):
    if y.sum() == 0:
        return 0.5
    pr, rc, th = precision_recall_curve(y, p)
    f1 = 2 * pr * rc / np.clip(pr + rc, 1e-9, None)
    return float(th[np.argmax(f1[:-1])]) if len(th) else 0.5


def metrics(y, p, thr):
    pred = p >= thr
    tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum()); tn = int((~pred & (y == 0)).sum())
    prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    return dict(precision=prec, recall=rec, f1=2 * prec * rec / max(prec + rec, 1e-9),
                fpr=fp / max(fp + tn, 1), tp=tp, fp=fp, fn=fn, tn=tn,
                ap=float(average_precision_score(y, p)) if y.sum() else float("nan"),
                auroc=float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else float("nan"))


@torch.no_grad()
def predict(model, x, batch=256):
    model.eval()
    out = []
    for i in range(0, len(x), batch):
        with torch.autocast(DEV.type, enabled=DEV.type == "cuda"):
            logits = model(x[i:i + batch].to(DEV).float())
        out.append(torch.sigmoid(logits.float().squeeze(1)).cpu().numpy())
    return np.concatenate(out)


# ----------------------------------------------------------------- entrenamiento
def run(kind, X, y, groups, seed, args):
    torch.manual_seed(seed); np.random.seed(seed)
    ch = C.CONFIGS[kind]
    tr, va, te = split_by_group(groups, seed)
    mean, std = channel_stats(X, tr, ch)
    xtr, xva, xte = (prep(X, i, ch, mean, std) for i in (tr, va, te))
    ytr = torch.from_numpy(y[tr]); yva, yte = y[va], y[te]

    model = build_model(len(ch), args.pretrained).to(DEV)
    n_params = sum(p.numel() for p in model.parameters())
    pos = float(y[tr].sum())
    crit = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([(len(tr) - pos) / max(pos, 1.0)], device=DEV))
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    scaler = torch.amp.GradScaler(enabled=DEV.type == "cuda")
    loader = DataLoader(TensorDataset(xtr, ytr), batch_size=args.batch, shuffle=True)

    best, best_state = -1.0, None
    for ep in range(args.epochs):
        model.train()
        for xb, yb in loader:
            xb, yb = xb.to(DEV).float(), yb.to(DEV)
            if np.random.rand() < 0.5: xb = torch.flip(xb, [3])
            if np.random.rand() < 0.5: xb = torch.flip(xb, [2])
            xb = torch.rot90(xb, int(np.random.randint(4)), [2, 3])
            opt.zero_grad(set_to_none=True)
            with torch.autocast(DEV.type, enabled=DEV.type == "cuda"):
                loss = crit(model(xb).float().squeeze(1), yb)
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
        sched.step()
        pv = predict(model, xva)
        score = average_precision_score(yva, pv) if yva.sum() else 0.0
        if score > best:
            best, best_state = score, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        print(f"  [{kind} seed{seed}] ép {ep + 1}/{args.epochs} loss {loss.item():.4f} val-AP {score:.3f}")

    model.load_state_dict(best_state)
    thr = threshold_max_f1(yva, predict(model, xva))             # umbral elegido con validación
    res = metrics(yte, predict(model, xte), thr)

    opt_pos = [i for i, c in enumerate(ch) if c in C.OPTICAL_IDX]
    mask = occlusion_masks(len(te), xte.shape[2], seed=1234 + seed)   # misma nube para ambas configs
    xocc = xte.clone()
    for pos_i in opt_pos:
        xocc[:, pos_i][mask] = 0                                  # 0 = media del canal tras normalizar
    occ = metrics(yte, predict(model, xocc), thr)

    ckpt = dict(state=best_state, mean=mean, std=std, threshold=thr, kind=kind, channels=ch,
                pretrained=args.pretrained)
    out = dict(kind=kind, seed=seed, params=n_params, threshold=thr, test=res, occluded=occ,
               n_test=int(len(te)), test_pos=int(yte.sum()))
    return out, ckpt


# ----------------------------------------------------------------- resumen y veredicto
def summarize(results):
    rows = []
    for kind, rs in results.items():
        for m in ("precision", "recall", "f1", "fpr", "ap", "auroc"):
            v = [r["test"][m] for r in rs]
            rows.append(dict(config=kind, condition="test", metric=m, mean=np.nanmean(v), std=np.nanstd(v)))
            v = [r["occluded"][m] for r in rs]
            rows.append(dict(config=kind, condition="occluded", metric=m, mean=np.nanmean(v), std=np.nanstd(v)))
    return pd.DataFrame(rows)


def verdict(results):
    A, B = results["optical"], results["fusion"]
    d = lambda cond, m: [b[cond][m] - a[cond][m] for a, b in zip(A, B)]
    d_ap, d_f1, d_ap_occ = d("test", "ap"), d("test", "f1"), d("occluded", "ap")
    n = len(A)
    need = (2 * n + 2) // 3
    m = {k: float(np.nanmean([r["test"][k] for r in B])) for k in ("precision", "recall", "fpr")}
    ok_thr = m["recall"] >= 0.75 and m["precision"] >= 0.70 and m["fpr"] <= 0.20
    beats = float(np.nanmean(d_ap)) > 0 and sum(x > 0 for x in d_ap) >= need
    robust = float(np.nanmean(d_ap_occ)) > 0 and sum(x > 0 for x in d_ap_occ) >= need
    return dict(fusion_means=m, delta_ap=d_ap, delta_f1=d_f1, delta_ap_occluded=d_ap_occ,
                delta_ap_mean=float(np.nanmean(d_ap)), delta_ap_occluded_mean=float(np.nanmean(d_ap_occ)),
                meets_thresholds=bool(ok_thr), fusion_beats_optical=bool(beats),
                fusion_more_robust_to_occlusion=bool(robust), passes=bool(ok_thr and beats))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(C.DATASET_DIR))
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--pretrained", action="store_true", help="init ImageNet (requiere descarga)")
    args = ap.parse_args()

    X, y, meta = load(args.data)
    groups = make_groups(meta)
    print(f"Dispositivo: {DEV} | parches {X.shape} | positivos {int(y.sum())} ({y.mean():.1%})")
    Path(C.RESULTS_DIR).mkdir(exist_ok=True); Path(C.MODELS_DIR).mkdir(exist_ok=True)

    results = {"optical": [], "fusion": []}
    for seed in range(args.seeds):
        for kind in ("optical", "fusion"):
            res, ckpt = run(kind, X, y, groups, seed, args)
            results[kind].append(res)
            if seed == 0:
                torch.save(ckpt, Path(C.MODELS_DIR) / f"{kind}.pt")

    df = summarize(results)
    df.to_csv(Path(C.RESULTS_DIR) / "summary.csv", index=False)
    v = verdict(results)
    out = dict(args=vars(args), runs=results, verdict=v, params={k: r[0]["params"] for k, r in results.items()})
    (Path(C.RESULTS_DIR) / "results.json").write_text(json.dumps(out, indent=2, default=float))

    pd.set_option("display.float_format", "{:.3f}".format)
    print("\n=== Media entre semillas ===")
    print(df.pivot_table(index=["condition", "metric"], columns="config", values="mean"))
    print("\nParámetros:", out["params"])
    print("\nVeredicto:", json.dumps(v, indent=2))
    print("\nGuardado en results/summary.csv, results/results.json y models/*.pt (semilla 0)")


if __name__ == "__main__":
    main()
