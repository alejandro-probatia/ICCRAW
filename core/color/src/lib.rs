use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct Lab {
    pub l: f64,
    pub a: f64,
    pub b: f64,
}

impl Lab {
    pub const fn new(l: f64, a: f64, b: f64) -> Self {
        Self { l, a, b }
    }
}

pub fn delta_e76(lhs: Lab, rhs: Lab) -> f64 {
    ((lhs.l - rhs.l).powi(2) + (lhs.a - rhs.a).powi(2) + (lhs.b - rhs.b).powi(2)).sqrt()
}

pub fn delta_e2000(lhs: Lab, rhs: Lab) -> f64 {
    let k_l = 1.0;
    let k_c = 1.0;
    let k_h = 1.0;

    let c1 = (lhs.a.powi(2) + lhs.b.powi(2)).sqrt();
    let c2 = (rhs.a.powi(2) + rhs.b.powi(2)).sqrt();
    let c_bar = (c1 + c2) / 2.0;

    let c_bar7 = c_bar.powi(7);
    let g = 0.5 * (1.0 - (c_bar7 / (c_bar7 + 25_f64.powi(7))).sqrt());

    let a1_prime = (1.0 + g) * lhs.a;
    let a2_prime = (1.0 + g) * rhs.a;

    let c1_prime = (a1_prime.powi(2) + lhs.b.powi(2)).sqrt();
    let c2_prime = (a2_prime.powi(2) + rhs.b.powi(2)).sqrt();

    let h1_prime = hue_angle_degrees(lhs.b, a1_prime);
    let h2_prime = hue_angle_degrees(rhs.b, a2_prime);

    let delta_l_prime = rhs.l - lhs.l;
    let delta_c_prime = c2_prime - c1_prime;

    let delta_h_prime = if c1_prime * c2_prime == 0.0 {
        0.0
    } else if (h2_prime - h1_prime).abs() <= 180.0 {
        h2_prime - h1_prime
    } else if h2_prime <= h1_prime {
        h2_prime - h1_prime + 360.0
    } else {
        h2_prime - h1_prime - 360.0
    };

    let delta_big_h_prime = 2.0 * (c1_prime * c2_prime).sqrt() * ((delta_h_prime.to_radians()) / 2.0).sin();

    let l_bar_prime = (lhs.l + rhs.l) / 2.0;
    let c_bar_prime = (c1_prime + c2_prime) / 2.0;

    let h_bar_prime = if c1_prime * c2_prime == 0.0 {
        h1_prime + h2_prime
    } else if (h1_prime - h2_prime).abs() <= 180.0 {
        (h1_prime + h2_prime) / 2.0
    } else if h1_prime + h2_prime < 360.0 {
        (h1_prime + h2_prime + 360.0) / 2.0
    } else {
        (h1_prime + h2_prime - 360.0) / 2.0
    };

    let t = 1.0
        - 0.17 * (h_bar_prime - 30.0).to_radians().cos()
        + 0.24 * (2.0 * h_bar_prime).to_radians().cos()
        + 0.32 * (3.0 * h_bar_prime + 6.0).to_radians().cos()
        - 0.20 * (4.0 * h_bar_prime - 63.0).to_radians().cos();

    let delta_theta = 30.0 * (-(((h_bar_prime - 275.0) / 25.0).powi(2))).exp();
    let r_c = 2.0 * ((c_bar_prime.powi(7)) / (c_bar_prime.powi(7) + 25_f64.powi(7))).sqrt();

    let s_l = 1.0 + ((0.015 * (l_bar_prime - 50.0).powi(2)) / (20.0 + (l_bar_prime - 50.0).powi(2)).sqrt());
    let s_c = 1.0 + 0.045 * c_bar_prime;
    let s_h = 1.0 + 0.015 * c_bar_prime * t;

    let r_t = -(2.0 * delta_theta).to_radians().sin() * r_c;

    let l_term = delta_l_prime / (k_l * s_l);
    let c_term = delta_c_prime / (k_c * s_c);
    let h_term = delta_big_h_prime / (k_h * s_h);

    (l_term.powi(2) + c_term.powi(2) + h_term.powi(2) + r_t * c_term * h_term).sqrt()
}

fn hue_angle_degrees(b: f64, a_prime: f64) -> f64 {
    let mut hue = b.atan2(a_prime).to_degrees();
    if hue < 0.0 {
        hue += 360.0;
    }
    hue
}

#[cfg(test)]
mod tests {
    use super::{delta_e2000, delta_e76, Lab};

    #[test]
    fn delta_e76_zero_for_equal_values() {
        let lab = Lab::new(50.0, 10.0, -20.0);
        assert_eq!(delta_e76(lab, lab), 0.0);
    }

    #[test]
    fn delta_e2000_matches_known_pair() {
        // From Sharma et al. CIEDE2000 supplementary data set, pair #1.
        let lhs = Lab::new(50.0, 2.6772, -79.7751);
        let rhs = Lab::new(50.0, 0.0, -82.7485);
        let de = delta_e2000(lhs, rhs);
        assert!((de - 2.0425).abs() < 0.0005, "deltaE2000 mismatch: {}", de);
    }
}
