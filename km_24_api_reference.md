# KM24 API Reference

Denne reference samler alle kendte endpoints fra KM24-API'et med formål og brug.

---

## 🔐 Authentication
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/token/pair` | **POST** | Login med e-mail og password → giver JWT access/refresh tokens |
| `/api/token/refresh` | **POST** | Fornyer access token |
| `/api/token/verify` | **POST** | Tjekker om token stadig er gyldig |
| `/api/token/logout` | **POST** | Logger ud og ugyldiggør token |

---

## 📦 Modules
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/modules/basic` | **GET** | Hent alle 45 moduler (fx Tinglysning, Udbud, Regnskaber) |
| `/api/modules/detailed` | **GET** | Hent moduler inkl. alle detaljer og metadata |
| `/api/modules/basic/{module_id}` | **GET** | Hent ét specifikt modul + dets underkategorier |
| `/api/modules/{module_id}/toggle-active` | **POST** | Aktivér/deaktivér et modul |
| `/api/modules/timings` | **GET/PUT/DELETE** | Læs, opdater eller slet konfiguration for hvornår moduler opdateres |

---

## 🧾 Companies
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/companies/add/search` | **GET** | Søg efter virksomheder (CVR) |
| `/api/companies/add/new` | **POST** | Tilføj ny virksomhed til overvågning |
| `/api/companies/main/download-subscriptions` | **GET** | Download alle virksomhedsabonnementer |
| `/api/companies/main/edit-search-string/{cvr}` | **PUT** | Redigér søgestrengen for en virksomhed |
| `/api/companies/main/forms` | **GET** | Hent formularer til virksomhedshåndtering |

---

## 🔍 Hits (Resultater)
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/hits` | **GET** | Hent overvågningsresultater (“hits”) fra valgfrit modul |
| `/api/hits/look-preferences` | **GET** | Hent brugerens visnings-præferencer for hits |
| `/api/hits/set-hit-look-preference` | **PUT** | Opdatér præferencer for visning af hits |
| `/api/hits/set-preference` | **PUT** | Sæt generelle hit-præferencer |

---

## 👤 Persons
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/persons/search` | **GET** | Søg efter personer i databasen |

---

## 🌐 Domains
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/domains/search` | **GET** | Søg efter internetdomæner (.dk) |

---

## 📊 Stats & Analytics
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/stats/hits-per-module` | **GET** | Antal hits pr. modul over tid |
| `/api/stats/hits-by-user` | **GET** | Antal hits pr. bruger |
| `/api/stats/users-per-module` | **GET** | Antal brugere pr. modul |

---

## ⚙️ Underkategorier
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/generic-values/{modulePartId}` | **GET** | Hent underkategorier (fx typer, reaktioner, smileyniveauer) |
| `/api/web-sources/categories/{moduleId}` | **GET** | Hent webkilder knyttet til et modul (fx medier, ministerier) |

---

## 🗒️ News
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/news` | **GET** | Hent nyheder fra KM24 |
| `/api/news/sign-up-newsletter` | **POST** | Tilmeld nyhedsbrev |

---

## 🌍 Languages
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/languages` | **GET** | Liste over tilgængelige sprog (da/en) |
| `/api/languages/{language}` | **PUT** | Skift brugerens sprog |

---

## 🧠 Super Admin (kun for administratorer)
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/super-admin/empty-cache` | **DELETE** | Tøm hele systemets cache (⚠ farligt) |
| `/api/super-admin/change-my-organisation` | **PUT** | Skift organisation for bruger |

---

## 🔗 Dokumentation
| Endpoint | Metode | Funktion |
|-----------|---------|-----------|
| `/api/docs/` | **GET** | Swagger-UI (interaktiv dokumentation) |
| `/api/schema.json` | **GET** | OpenAPI-schema i JSON-format |

---

### Note
- Alle kald kræver **HTTPS** og gyldig `X-API-Key` eller JWT-token.
- Pagination bruges på de fleste endpoints: `page`, `page_size`, `next`, `previous`.
- Ingen observeret rate limiting i test (0.25–0.8s response time).

---

**Kilde:** Intern analyse og reverse-engineering af KM24 API (2025).

