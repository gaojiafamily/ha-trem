<h1 align="center">Taiwan Real-time Earthquake Monitoring for HA</h1>

![Logo](https://raw.githubusercontent.com/gaojiafamily/ha-trem/master/docs/media/logo.png)

[![GitHub Release][releases-shield]][releases]
[![hacs_custom][hacs_custom_shield]][hacs_custom]
[![License][license-shield]](LICENSE)

[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![Contributors][contributors-shield]][contributors-url]

[![BuyMeCoffee][buymecoffee-shield]][buymecoffee]

<hr>

English | [繁體中文](README_zhHant.md)<br>


## Screenshots

![config_flow_image](https://github.com/J1A-T13N/ha-trem/assets/29163857/a6f4cc49-0521-4f27-a894-9fb1273be1cf)
![simulator_earthquake_demo](https://github.com/J1A-T13N/ha-trem/assets/29163857/b62dab7a-2935-4477-8297-f7e275df0a81)

<hr>
<br>


> [!IMPORTANT]
>The source of earthquake early warning is provided by ExpTech Studio and is for reference only.<br>
>The actual results are subject to the content published by [CWA](https://scweb.cwa.gov.tw/en-US).

<hr>
<br>


## Feature

- [x] Isoseismal map image (can also be saved as file).
- [x] Simulator earthquake service.
- [x] RTS Notification (Exptech VIP Only).
- [x] Tsunami Notification (Exptech VIP Only).

<hr>
<br>


## Available

| Environment | Home Assistant OS | Home Assistant Core | Home Assistant Supervisor |
| :------------: | :------------: | :------------: | :------------: |
| Virtual Machine[^1] | :heavy_check_mark: |  |  |
| Container |  | :heavy_check_mark: | :question:[^2] |
| Virtual Environment |  | :heavy_check_mark: |  |
| Physics Machine[^3] | :question:[^4] | :heavy_minus_sign:[^5] | :question:[^2] |

:heavy_check_mark: Available<br>
:heavy_multiplication_x: Unavailable<br>
:question: Untested<br>
:heavy_minus_sign: See footnotes<br>
[^1]: Virtual Machine may include but not limited to: VirtualBox、Unraid、KVM/Proxmox、UTM...etc.
[^2]: If your installation method is [it](https://github.com/home-assistant/supervised-installer).
[^3]: Physics Machine may include but not limited to: Raspberry Pi、Home Assistant Green、Home Assistant Yellow...etc.
[^4]: So far, only known rpi4 4GB is available.
[^5]: If your installation method on other systems, Hope you can provide feedback.

<hr>
<br>


## Prerequisite (if you're using HAOS)
**Manual install dependencies see [here](docs/haos_guide.md).**

> [!IMPORTANT]
> This custom component installation is considered advanced<br>
> should only be used if one is an expert in managing a Linux operating system.

> /tmp is mounted noexec on HAOS so it can't compile, A [workaround](https://github.com/home-assistant/core/issues/118717) is to do this inside the container.

<hr>
<br>


## Installation

### Using [HACS](https://hacs.xyz/) (recommended)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gaojiafamily&repository=ha-trem&category=Integration)

### Manual
1. Create `config/custom_components` folder if not existing.
2. Copy `trem` into `custom_components` folder.

<hr>
<br>


## Config

**Please use the config flow of Home Assistant.**

1. With GUI. Configuration > Integration > Add Integration > Taiwan Real-time Earthquake Monitoring
   - If the integration didn't show up in the list please REFRESH the page
   - If the integration is still not in the list, you need to clear the browser cache.

*A Region code can be search [here](https://github.com/ExpTechTW/API/blob/master/resource/region.json).*<br>
<hr>
<br>


## Data Source
- [x] HTTPS API (or use your self-server)
- [x] Websocket. (Exptech VIP Only)

### HTTPS API
| Node               | Description                                 |
| :----------------: | :-----------------------------------------: |
| tainan_cache_limit | The number of requests is limited           |
| tainan_cache       | Available to all users                      |
| taipe_cache_limit  | The number of requests is limited           |
| taipe_cache        | Available to all users                      |
| taipei_limit       | The number of requests is limited           |
| taipei             | The data is real-time but the load is high  |
| taipei_2           | The data is real-time but the load is high  |
| pingtung_limit     | The number of requests is limited           |
| pingtung           | The data is real-time but the load is high  |
| pingtung_2         | The data is real-time but the load is high  |

### Websocket
**Exptech VIP Only**
You can goto [https://exptech.com.tw/pricing](https://exptech.com.tw/pricing) to subscribe.

*An API server can be monitored [here](https://status.exptech.dev/).*<br>


## Known issues

1. Not support Home Assistant 2024.8 and higher yet.

<hr>
<br>


## Contribution

- ExpTech Studio `Data Source`
- watermelon1024 `Contributor`
- kukuxx `Test Partner`

<p>I would like to thank everyone who has helped me and every partner in the community for their generous help.</p>

<hr>
<br>


## Donate

| Buy me a coffee | LINE Bank | JKao Pay |
| :------------: | :------------: | :------------: |
| <img src="https://github.com/J1A-T13N/ha-trem/assets/29163857/e61afedc-1fce-47a1-a6c3-00bc1a9a5329" alt="Buy me a coffee" height="200" width="200">  | <img src="https://github.com/J1A-T13N/ha-trem/assets/29163857/a0af96ea-7e03-47de-83ae-3c11b2e27c57" alt="Line Bank" height="200" width="200">  | <img src="https://github.com/J1A-T13N/ha-trem/assets/29163857/333def56-cf08-4f8e-a188-9067cc4f63d9" alt="JKo Pay" height="200" width="200">  |

<hr>
<br>


## License
AGPL-3.0 license

**2024-08-15 Agreement reached with ExpTech Studio.**


[releases-shield]: https://img.shields.io/github/release/gaojiafamily/ha-trem.svg?style=for-the-badge
[releases]: https://github.com/gaojiafamily/ha-trem/releases
[hacs_custom_shield]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs_custom]: https://hacs.xyz/docs/faq/custom_repositories
[stars-shield]: https://img.shields.io/github/stars/gaojiafamily/ha-trem.svg?style=for-the-badge
[stars-url]: https://github.com/gaojiafamily/ha-trem/stargazers
[issues-shield]: https://img.shields.io/github/issues/gaojiafamily/ha-trem.svg?style=for-the-badge
[issues-url]: https://github.com/gaojiafamily/ha-trem/issues
[contributors-shield]: https://img.shields.io/github/contributors/gaojiafamily/ha-trem.svg?style=for-the-badge
[contributors-url]: https://github.com/gaojiafamily/ha-trem/graphs/contributors
[license-shield]: https://img.shields.io/github/license/gaojiafamily/ha-trem.svg?style=for-the-badge
[buymecoffee-shield]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[buymecoffee]: https://www.buymeacoffee.com/j1at13n
