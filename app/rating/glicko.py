"""
Glicko-2 rating engine.

Reference: Mark Glickman, "Example of the Glicko-2 system" (2012).
http://www.glicko.net/glicko/glicko2.pdf

All matches are processed chronologically in a single rating period.
"""

import math
from app.rating.base import RatingEngine

# Glicko-2 constants
INITIAL_R = 1500.0      # initial rating (Glicko scale)
INITIAL_RD = 350.0      # initial rating deviation
INITIAL_VOL = 0.06      # initial volatility
TAU = 0.5               # system constant (controls volatility change)
EPSILON = 0.000001      # convergence tolerance


def _g(phi: float) -> float:
    """g function from Glicko-2."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi ** 2 / math.pi ** 2)


def _E(mu: float, mu_j: float, phi_j: float) -> float:
    """Expected score function."""
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _scale_to_glicko2(r: float, rd: float) -> tuple[float, float]:
    """Convert Glicko (r, RD) to Glicko-2 (mu, phi)."""
    mu = (r - 1500.0) / 173.7178
    phi = rd / 173.7178
    return mu, phi


def _scale_from_glicko2(mu: float, phi: float) -> tuple[float, float]:
    """Convert Glicko-2 (mu, phi) to Glicko (r, RD)."""
    r = 173.7178 * mu + 1500.0
    rd = 173.7178 * phi
    return r, rd


def _update_player(mu: float, phi: float, sigma: float,
                   outcomes: list[tuple]) -> tuple[float, float, float]:
    """
    Update one player's Glicko-2 rating given a list of outcomes.
    outcomes: list of (mu_j, phi_j, s_j) where s_j is 0/0.5/1.
    Returns (new_mu, new_phi, new_sigma).
    """
    if not outcomes:
        # No games played: only RD increases
        phi_star = math.sqrt(phi ** 2 + sigma ** 2)
        return mu, phi_star, sigma

    # Step 3: compute v
    v_inv = sum(
        _g(phi_j) ** 2 * _E(mu, mu_j, phi_j) * (1 - _E(mu, mu_j, phi_j))
        for mu_j, phi_j, _ in outcomes
    )
    v = 1.0 / v_inv

    # Step 4: compute delta
    delta = v * sum(
        _g(phi_j) * (s_j - _E(mu, mu_j, phi_j))
        for mu_j, phi_j, s_j in outcomes
    )

    # Step 5: update volatility via Illinois algorithm
    a = math.log(sigma ** 2)

    def f(x):
        ex = math.exp(x)
        d2 = phi ** 2 + v + ex
        return (ex * (delta ** 2 - phi ** 2 - v - ex) / (2.0 * d2 ** 2)
                - (x - a) / TAU ** 2)

    A = a
    if delta ** 2 > phi ** 2 + v:
        B = math.log(delta ** 2 - phi ** 2 - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        B = a - k * TAU

    fA = f(A)
    fB = f(B)

    for _ in range(100):
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)
        if fC * fB <= 0:
            A, fA = B, fB
        else:
            fA = fA / 2.0
        B, fB = C, fC
        if abs(B - A) < EPSILON:
            break

    new_sigma = math.exp(A / 2.0)

    # Step 6: update phi
    phi_star = math.sqrt(phi ** 2 + new_sigma ** 2)

    # Step 7: update phi and mu
    phi_prime = 1.0 / math.sqrt(1.0 / phi_star ** 2 + 1.0 / v)
    mu_prime = mu + phi_prime ** 2 * sum(
        _g(phi_j) * (s_j - _E(mu, mu_j, phi_j))
        for mu_j, phi_j, s_j in outcomes
    )

    return mu_prime, phi_prime, new_sigma


class Glicko2Engine(RatingEngine):
    name = "glicko2"

    def compute_snapshots(self, matches: list, players: list) -> list[dict]:
        """
        Process all matches in one rating period chronologically.
        Each match updates ratings immediately (sequential single-period).
        """
        # Initialize state
        state = {
            p.id: {
                "r": p.glicko_rating if p.glicko_rating else INITIAL_R,
                "rd": p.glicko_rd if p.glicko_rd else INITIAL_RD,
                "vol": p.glicko_vol if p.glicko_vol else INITIAL_VOL,
            }
            for p in players
        }

        snapshots = []
        sorted_matches = sorted(matches, key=lambda m: (m.match_date, m.id))

        for match in sorted_matches:
            s1 = state[match.player1_id]
            s2 = state[match.player2_id]

            r1, rd1, vol1 = s1["r"], s1["rd"], s1["vol"]
            r2, rd2, vol2 = s2["r"], s2["rd"], s2["vol"]

            mu1, phi1 = _scale_to_glicko2(r1, rd1)
            mu2, phi2 = _scale_to_glicko2(r2, rd2)

            if match.score1 > match.score2:
                actual1, actual2 = 1.0, 0.0
            elif match.score1 < match.score2:
                actual1, actual2 = 0.0, 1.0
            else:
                actual1, actual2 = 0.5, 0.5

            # Update player 1 based on match vs player 2
            new_mu1, new_phi1, new_vol1 = _update_player(
                mu1, phi1, vol1, [(mu2, phi2, actual1)]
            )
            # Update player 2 based on match vs player 1
            new_mu2, new_phi2, new_vol2 = _update_player(
                mu2, phi2, vol2, [(mu1, phi1, actual2)]
            )

            new_r1, new_rd1 = _scale_from_glicko2(new_mu1, new_phi1)
            new_r2, new_rd2 = _scale_from_glicko2(new_mu2, new_phi2)

            expected1 = _E(mu1, mu2, phi2)
            expected2 = _E(mu2, mu1, phi1)

            snapshots.append({
                "match_id": match.id,
                "player_id": match.player1_id,
                "system_name": "glicko2",
                "rating_before": round(r1, 2),
                "rating_after": round(new_r1, 2),
                "expected_score": round(expected1, 4),
                "actual_score": actual1,
                "delta": round(new_r1 - r1, 2),
                "rd_before": round(rd1, 2),
                "rd_after": round(new_rd1, 2),
            })
            snapshots.append({
                "match_id": match.id,
                "player_id": match.player2_id,
                "system_name": "glicko2",
                "rating_before": round(r2, 2),
                "rating_after": round(new_r2, 2),
                "expected_score": round(expected2, 4),
                "actual_score": actual2,
                "delta": round(new_r2 - r2, 2),
                "rd_before": round(rd2, 2),
                "rd_after": round(new_rd2, 2),
            })

            state[match.player1_id] = {"r": new_r1, "rd": new_rd1, "vol": new_vol1}
            state[match.player2_id] = {"r": new_r2, "rd": new_rd2, "vol": new_vol2}

        return snapshots

    def final_ratings(self, matches: list, players: list) -> dict[int, float]:
        snapshots = self.compute_snapshots(matches, players)
        # Start from initial ratings
        ratings = {p.id: p.glicko_rating if p.glicko_rating else INITIAL_R for p in players}
        for snap in snapshots:
            ratings[snap["player_id"]] = snap["rating_after"]
        return ratings

    def final_state(self, matches: list, players: list) -> dict[int, dict]:
        """Return {player_id: {r, rd, vol}} after processing all matches."""
        state = {
            p.id: {
                "r": INITIAL_R,
                "rd": INITIAL_RD,
                "vol": INITIAL_VOL,
            }
            for p in players
        }
        sorted_matches = sorted(matches, key=lambda m: (m.match_date, m.id))
        for match in sorted_matches:
            s1 = state[match.player1_id]
            s2 = state[match.player2_id]
            mu1, phi1 = _scale_to_glicko2(s1["r"], s1["rd"])
            mu2, phi2 = _scale_to_glicko2(s2["r"], s2["rd"])
            if match.score1 > match.score2:
                a1, a2 = 1.0, 0.0
            elif match.score1 < match.score2:
                a1, a2 = 0.0, 1.0
            else:
                a1, a2 = 0.5, 0.5
            new_mu1, new_phi1, new_vol1 = _update_player(mu1, phi1, s1["vol"], [(mu2, phi2, a1)])
            new_mu2, new_phi2, new_vol2 = _update_player(mu2, phi2, s2["vol"], [(mu1, phi1, a2)])
            new_r1, new_rd1 = _scale_from_glicko2(new_mu1, new_phi1)
            new_r2, new_rd2 = _scale_from_glicko2(new_mu2, new_phi2)
            state[match.player1_id] = {"r": new_r1, "rd": new_rd1, "vol": new_vol1}
            state[match.player2_id] = {"r": new_r2, "rd": new_rd2, "vol": new_vol2}
        return state

    def win_probability(self, r1: float, rd1: float, r2: float, rd2: float) -> float:
        """Glicko-2 win probability for player 1."""
        mu1, phi1 = _scale_to_glicko2(r1, rd1)
        mu2, phi2 = _scale_to_glicko2(r2, rd2)
        return _E(mu1, mu2, phi2)
