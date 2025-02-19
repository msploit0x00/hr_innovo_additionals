# calculate_variable_tax

import frappe
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from hrms.payroll.doctype.salary_slip.salary_slip import set_loan_repayment
from frappe.utils import flt,getdate
from frappe.query_builder.functions import Count, Sum
class CustomSalarySlip(SalarySlip):
    def calculate_net_pay(self, skip_tax_breakup_computation: bool = False):
      def set_gross_pay_and_base_gross_pay():
        self.gross_pay = self.get_component_totals("earnings", depends_on_payment_days=1)
        self.base_gross_pay = flt(
          flt(self.gross_pay) * flt(self.exchange_rate), self.precision("base_gross_pay")
        )

      if self.salary_structure:
        self.calculate_component_amounts("earnings")

      # get remaining numbers of sub-period (period for which one salary is processed)
      if self.payroll_period:
        self.remaining_sub_periods = 12
  
        print(f"self.remaining_sub_periods\n{self.remaining_sub_periods }")
      set_gross_pay_and_base_gross_pay()

      if self.salary_structure:
        self.calculate_component_amounts("deductions")

      set_loan_repayment(self)

      self.set_precision_for_component_amounts()
      self.set_net_pay()
      if not skip_tax_breakup_computation:
        self.compute_income_tax_breakup()
    def compute_taxable_earnings_for_year(self):
      # get taxable_earnings, opening_taxable_earning, paid_taxes for previous period
      self.previous_taxable_earnings, exempted_amount = self.get_taxable_earnings_for_prev_period(
        self.payroll_period.start_date, self.start_date, self.tax_slab.allow_tax_exemption
      )

      self.previous_taxable_earnings_before_exemption = self.previous_taxable_earnings + exempted_amount

      self.compute_current_and_future_taxable_earnings()

      # Deduct taxes forcefully for unsubmitted tax exemption proof and unclaimed benefits in the last period
      if self.payroll_period.end_date <= getdate(self.end_date):
        self.deduct_tax_for_unsubmitted_tax_exemption_proof = 1
        self.deduct_tax_for_unclaimed_employee_benefits = 1

      # Get taxable unclaimed benefits
      self.unclaimed_taxable_benefits = 0
      if self.deduct_tax_for_unclaimed_employee_benefits:
        self.unclaimed_taxable_benefits = self.calculate_unclaimed_taxable_benefits()

      # Total exemption amount based on tax exemption declaration
      self.total_exemption_amount = self.get_total_exemption_amount()

      # Employee Other Incomes
      self.previous_axable_earnings=0
      self.other_incomes = self.get_income_form_other_sources() or 0.0
      print(f"previous_taxable_earnings(33) =========={self.previous_taxable_earnings}")
      print(f"current_structured_taxable_earnings(33) =========={self.current_structured_taxable_earnings}")
      print(f"future_structured_taxable_earnings(33) =========={self.future_structured_taxable_earnings}")
      print(f"previous_taxable_earnings(33) =========={self.future_structured_taxable_earnings}")
      print(f"previous_taxable_earnings(33) =========={self.previous_taxable_earnings}")
      print(f"previous_taxable_earnings(33) =========={self.previous_taxable_earnings}")
      print(f"previous_taxable_earnings(33) =========={self.previous_taxable_earnings}")
      # Total taxable earnings including additional and other incomes
      self.total_taxable_earnings = (
        self.previous_axable_earnings
        + self.current_structured_taxable_earnings
        + self.future_structured_taxable_earnings
        + self.current_additional_earnings
        + self.other_incomes
        + self.unclaimed_taxable_benefits
        - self.total_exemption_amount
      )


      # Total taxable earnings without additional earnings with full tax
      self.total_taxable_earnings_without_full_tax_addl_components = (
        self.total_taxable_earnings - self.current_additional_earnings_with_full_tax
      )
        