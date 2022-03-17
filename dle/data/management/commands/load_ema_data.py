from django.core.management.base import BaseCommand, CommandError
from data.models import DrugLabel, LabelProduct, ProductSection
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.conf import settings
import requests
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
import re

# pip install bs4
# pip install pymupdf

EMA_DATA_URL = "https://www.ema.europa.eu/en/medicines/field_ema_web_categories%253Aname_field/Human/ema_group_types/ema_medicine"

# 3 sample data urls/pdfs for testing
URL_1 = "https://www.ema.europa.eu/en/medicines/human/EPAR/skilarence"
PDF_1 = "https://www.ema.europa.eu/en/documents/product-information/skilarence-epar-product-information_en.pdf"

URL_2 = "https://www.ema.europa.eu/en/medicines/human/EPAR/lyrica"
PDF_2 = "https://www.ema.europa.eu/documents/product-information/lyrica-epar-product-information_en.pdf"

URL_3 = "https://www.ema.europa.eu/en/medicines/human/EPAR/ontilyv"
PDF_3 = "https://www.ema.europa.eu/documents/product-information/ontilyv-epar-product-information_en.pdf"

PDFS = [PDF_1, PDF_2, PDF_3]


class EmaSectionDef:
    """struct to hold info that helps us parse the Sections"""

    def __init__(self, start_text, end_text, name):
        self.start_text = start_text
        self.end_text = end_text
        self.name = name


# only doing a few to start
# these should be in order of how they appear in the pdf
EMA_PDF_PRODUCT_SECTIONS = [
    EmaSectionDef(
        "4.1 \nTherapeutic indications",
        "4.2 \nPosology and method of administration",
        "INDICATIONS",
    ),
    EmaSectionDef(
        "4.3 \nContraindications",
        "4.4 \nSpecial warnings and precautions for use",
        "CONTRA",
    ),
    EmaSectionDef(
        "4.4 \nSpecial warnings and precautions for use",
        "4.5 \nInteraction with other medicinal products and other forms of interaction",
        "WARN",
    ),
    EmaSectionDef(
        "4.6 \nFertility, pregnancy and lactation",
        "4.7 \nEffects on ability to drive and use machines",
        "PREG",
    ),
]

# runs with `python manage.py load_ema_data`
class Command(BaseCommand):
    help = "Loads data from EMA"

    def handle(self, *args, **options):
        # WIP

        dl = DrugLabel() # empty object to populate as we go
        dl.source = 'EMA'

        # grab the webpage
        response = requests.get(URL_1)
        soup = BeautifulSoup(response.text, 'html.parser')
        # self.stdout.write(soup.prettify())
        # self.stdout.write(repr(soup))

        # ref: https://www.crummy.com/software/BeautifulSoup/bs4/doc/

        # for now, we want to grab 6 things from the web page:
        # product_name
        # generic_name
        # version_date
        # source_product_number
        # marketer
        # url for product-information pdf

        # look in the "Authorisation details" section
        # "Name" => product_name
        # "Active substance" => generic_name
        # "Agency product number" => source_product_number
        # "Marketing-authorisation holder" => marketer

        # "Product information" section
        # product-information pdf
        # "Last updated: DD/MM/YYYY" # note EU has different date format from USA

        # look for the section
        tag = soup.find(id="authorisation-details-section")

        # product_name
        # find the 'td' cell that contains the 'Name' text
        cell = tag.find_next("td", string=re.compile(r"\sName\s"))
        # grab the text from the 'next sibling'
        str = cell.find_next_sibling().get_text(strip=True)
        # self.stdout.write(repr(str))
        # set it in our object
        dl.product_name = str

        # generic_name
        cell = tag.find_next("td", string=re.compile(r"\sActive substance\s"))
        str = cell.find_next_sibling().get_text(strip=True)
        dl.generic_name = str

        # source_product_number
        cell = tag.find_next("td", string=re.compile(r"\sAgency product number\s"))
        str = cell.find_next_sibling().get_text(strip=True)
        dl.source_product_number = str

        # marketer
        cell = tag.find_next("td", string=re.compile(r"\sMarketing-authorisation holder\s"))
        str = cell.find_next_sibling().get_text(strip=True)
        dl.marketer = str

        tag = soup.find(id="product-information-section")

        # # version_date
        # entry = tag.find_next(string=re.compile(r"Last updated:"))
        # self.stdout.write(repr(entry))
        #
        # # url for product-information pdf
        # entry = tag.find_next("a", string=re.compile(r"Product Information"))
        # self.stdout.write(repr(entry))

        self.stdout.write(repr(dl))

        return # TODO fix-a-lo

        # save pdf to default_storage / MEDIA_ROOT
        response = requests.get(PDF_1)
        filename = default_storage.save(
            settings.MEDIA_ROOT / "ema.pdf", ContentFile(response.content)
        )
        self.stdout.write(f"saved file to: {filename}")

        # populate raw_text with the contents of the pdf
        raw_text = ""
        with fitz.open(settings.MEDIA_ROOT / "ema.pdf") as pdf_doc:
            for page in pdf_doc:
                raw_text += page.get_text()

        # the sections are in order
        # so keep track of where to start the search in each iteration
        start_idx = 0
        for section in EMA_PDF_PRODUCT_SECTIONS:
            self.stdout.write(f"section.name: {section.name}")
            self.stdout.write(f"looking for section.start_text: {section.start_text}")
            idx = raw_text.find(section.start_text, start_idx)
            if idx == -1:
                self.stderr.write(self.style.ERROR("Unable to find section_start_text"))
                continue
            else:
                self.stdout.write(self.style.SUCCESS(f"Found section.start_text, idx: {idx}"))

            # look for section_end_text
            self.stdout.write(f"looking for section.end_text: {section.end_text}")
            end_idx = raw_text.find(section.end_text, idx)
            if end_idx == -1:
                self.stderr.write(self.style.ERROR("Unable to find section.end_text"))
                continue
            else:
                self.stdout.write(self.style.SUCCESS(f"Found section.end_text, end_idx: {end_idx}"))

            # the section_text is between idx and end_idx
            section_text = raw_text[idx: end_idx]
            self.stdout.write(f"found section_text: {section_text}")
            ps = ProductSection(
                # label_product=lp, # TODO need this
                section_name=section.name,
                section_text=section_text
            )
            # ps.save() # TODO

            # start search for next section after the end_idx of this section
            start_idx = end_idx

        # self.stdout.write(f"raw_text: {repr(raw_text)}")

        # delete the file when done
        default_storage.delete(filename)

        self.stdout.write(self.style.SUCCESS("Success"))
        return

        # ref: https://stackoverflow.com/a/64997181/1807627
        # ref: https://stackoverflow.com/q/9751197/1807627
        # ref: https://www.geeksforgeeks.org/how-to-scrape-all-pdf-files-in-a-website/

        # try to save to MEDIA dir, then open
        # ty: https://stackoverflow.com/a/63486976/1807627
        # https://github.com/pymupdf/PyMuPDF-Utilities/blob/master/text-extraction/PDF2Text.py
        # https://github.com/pymupdf/PyMuPDF/blob/master/fitz/fitz.i

    def load_fake_drug_label(self):
        # For now, just loading one dummy-label
        dl = DrugLabel(
            source="EMA",
            product_name="Diffusia",
            generic_name="lorem ipsem",
            version_date="2022-03-15",
            source_product_number="ABC-123-DO-RE-ME",
            raw_text="Fake raw label text",
            marketer="Landau Pharma",
        )
        dl.save()
        lp = LabelProduct(drug_label=dl)
        lp.save()
        ps = ProductSection(
            label_product=lp,
            section_name="INDICATIONS",
            section_text="Cures cognitive deficit disorder",
        )
        ps.save()
        ps = ProductSection(
            label_product=lp, section_name="WARN", section_text="May cause x, y, z"
        )
        ps.save()
        ps = ProductSection(
            label_product=lp, section_name="PREG", section_text="Good to go"
        )
        ps.save()
