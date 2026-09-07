# Local browser assets

Pinned assets served locally so navigation, forms, icons and charts do not require CDN access at runtime.

| Package | Version | Files | License |
| --- | --- | --- | --- |
| Bootstrap | 5.3.0 | bootstrap.min.css, bootstrap.bundle.min.js | LICENSE-bootstrap |
| Bootstrap Icons | 1.11.1 | bootstrap-icons.css, fonts/*.woff* | LICENSE-bootstrap-icons |
| Chart.js | 4.4.8 | chart.umd.js | LICENSE-chartjs |

Source: each named npm package at `https://cdn.jsdelivr.net/npm/<package>@<version>/`. CSS/JS headers retain upstream attribution. Bootstrap/icon versions preserve the existing interface dependency contract. Chart.js is now pinned and used only on the sensor page.
